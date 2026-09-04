"""Aplica créditos em contas a partir de eventos enviados por um provedor externo.

O provedor garante que cada evento tem um `event_id` estável, mas **não** garante
entrega única: o mesmo evento pode chegar mais de uma vez, inclusive em paralelo.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS applied_events (
    event_id     TEXT    PRIMARY KEY,
    account_id   TEXT    NOT NULL,
    amount_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id    TEXT    PRIMARY KEY,
    balance_cents INTEGER NOT NULL DEFAULT 0
);
"""

DATABASE_TIMEOUT_SECONDS = 5


class InvalidCreditError(Exception):
    """Raised when the incoming credit event is not valid."""


@dataclass
class CreditResult:
    applied: bool
    balance_cents: int


class CreditLedger:
    def __init__(self, database_path: str):
        self._database_path = database_path
        with self._transaction() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _transaction(self):
        conn = sqlite3.connect(self._database_path, timeout=DATABASE_TIMEOUT_SECONDS)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def apply_credit(
        self,
        event_id: str,
        account_id: str,
        amount_cents: int,
    ) -> CreditResult:
        ### 1. Validação
        if not event_id:
            raise InvalidCreditError("event_id não pode ser vazio")

        if not account_id:
            raise InvalidCreditError("account_id não pode ser vazio")

        if amount_cents <= 0:
            raise InvalidCreditError("amount_cents deve ser maior que zero")
        ### 2. Transação
        with self._transaction() as conn:   
            ### 3. Cria se inexistente
            conn.execute(
                "INSERT OR IGNORE INTO accounts (account_id, balance_cents)"
                " VALUES (?, 0)",
                (account_id,),
            )
            ### 4. Registra evento
            cursor = conn.execute(
                "INSERT OR IGNORE INTO applied_events (event_id, account_id, amount_cents)"
                " VALUES (?, ?, ?)",
                (event_id, account_id, amount_cents),
            )
            # 5. Verificar se foi aplicado
            applied = cursor.rowcount == 1

            # 6. Só atualizar saldo se for evento novo
            if applied:
                conn.execute(
                    """
                    UPDATE accounts
                    SET balance_cents = balance_cents + ?
                    WHERE account_id = ?
                    """,
                    (amount_cents, account_id),
                )

            # 7. Obter saldo dentro da mesma transação
            row = conn.execute(
                """
                SELECT balance_cents
                FROM accounts
                WHERE account_id = ?
                """,
                (account_id,),
            ).fetchone()

            balance_cents = row[0]

        return CreditResult(applied=applied, balance_cents=balance_cents)

    def balance(self, account_id: str) -> int:
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT balance_cents FROM accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()

        return row[0] if row else 0
