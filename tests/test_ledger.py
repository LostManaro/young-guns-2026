from ledger import CreditLedger, InvalidCreditError
import threading
import pytest

def test_applies_credit_once(ledger):
    result = ledger.apply_credit("evt-1", "acc-1", 1000)

    assert result.applied is True
    assert result.balance_cents == 1000
    assert ledger.balance("acc-1") == 1000


def test_different_events_accumulate(ledger):
    ledger.apply_credit("evt-1", "acc-1", 1000)
    ledger.apply_credit("evt-2", "acc-1", 250)

    assert ledger.balance("acc-1") == 1250


def test_accounts_are_independent(ledger):
    ledger.apply_credit("evt-1", "acc-1", 1000)
    ledger.apply_credit("evt-2", "acc-2", 700)

    assert ledger.balance("acc-1") == 1000
    assert ledger.balance("acc-2") == 700


def test_duplicate_event_is_applied_only_once(ledger):
    ledger.apply_credit("evt-1", "acc-1", 1000)
    result = ledger.apply_credit("evt-1", "acc-1", 1000)

    assert result.applied is False
    assert ledger.balance("acc-1") == 1000


def test_duplicate_event_is_ignored_after_restart(database_path):
    CreditLedger(database_path).apply_credit("evt-1", "acc-1", 1000)

    restarted = CreditLedger(database_path)
    result = restarted.apply_credit("evt-1", "acc-1", 1000)

    assert result.applied is False
    assert restarted.balance("acc-1") == 1000


def test_unknown_account_has_zero_balance(ledger):
    assert ledger.balance("acc-inexistente") == 0

def test_duplicate_event_is_applied_only_once_concurrently(database_path):
    ledger1 = CreditLedger(database_path)
    ledger2 = CreditLedger(database_path)

    barrier = threading.Barrier(2)
    results = []

    def apply_credit(ledger):
        barrier.wait()
        result = ledger.apply_credit("event-concurrent", "account-1", 100)
        results.append(result)

    thread1 = threading.Thread(target=apply_credit, args=(ledger1,))
    thread2 = threading.Thread(target=apply_credit, args=(ledger2,))

    thread1.start()
    thread2.start()

    thread1.join()
    thread2.join()

    assert sorted(result.applied for result in results) == [False, True]
    assert ledger1.balance("account-1") == 100

def test_invalid_event_can_be_reused(database_path):
    ledger = CreditLedger(database_path)

    with pytest.raises(InvalidCreditError):
        ledger.apply_credit("event-reuse", "account-1", -100)

    result = ledger.apply_credit("event-reuse", "account-1", 100)

    assert result.applied is True
    assert result.balance_cents == 100