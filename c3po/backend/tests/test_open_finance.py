from datetime import datetime, timedelta, timezone

import httpx

from app.config import Settings
from app.open_finance import OpenFinanceService


def test_bank_detection_uses_products_when_connector_is_generic() -> None:
    service = OpenFinanceService(Settings())

    assert service._detect_bank(
        {"connector": {"name": "MeuPluggy"}},
        [{"name": "BTG Pactual WM"}],
        [{"name": "BILLFISH FIA"}],
    ) == "btg"
    assert service._detect_bank(
        {"connector": {"name": "MeuPluggy"}},
        [{"name": "Banco Santander"}],
        [],
    ) == "santander"
    assert service._detect_bank(
        {"connector": {"name": "MeuPluggy"}},
        [{"name": "PERSONNALITE MC BLACK"}],
        [],
    ) == "itau"


def test_bank_snapshot_separates_cash_cards_investments_and_36_hour_statement() -> None:
    service = OpenFinanceService(Settings())
    now = datetime.now(timezone.utc)
    account = {
        "id": "account-1",
        "name": "BTG Banking",
        "number": "0001/1234-5",
        "type": "BANK",
        "subtype": "CHECKING_ACCOUNT",
        "balance": -125.50,
        "currencyCode": "BRL",
    }
    card = {
        "id": "card-1",
        "name": "BTG Ultrablack",
        "number": "2174",
        "type": "CREDIT",
        "subtype": "CREDIT_CARD",
        "balance": 7800,
        "currencyCode": "BRL",
    }
    bucket = {
        "items": [({"status": "UPDATED", "executionStatus": "SUCCESS", "lastUpdatedAt": now.isoformat()}, "recent", "Dados relidos agora.")],
        "accounts": [account, card],
        "investments": [
            {"id": "investment-1", "name": "BILLFISH FIA", "type": "MUTUAL_FUND", "amount": 22_000_000, "balance": 21_500_000, "currencyCode": "BRL"},
            {"id": "investment-closed", "name": "Closed CDB", "type": "FIXED_INCOME", "amount": 0, "balance": 0, "currencyCode": "BRL"},
        ],
        "transactions": [
            {"id": "recent", "date": (now - timedelta(hours=2)).isoformat(), "amount": -450, "description": "PIX enviado", "currencyCode": "BRL", "status": "POSTED", "_account": account},
            {"id": "old", "date": (now - timedelta(hours=40)).isoformat(), "amount": -20, "description": "Antiga", "currencyCode": "BRL", "status": "POSTED", "_account": account},
        ],
        "errors": [],
    }

    bank = service._build_bank("btg", bucket, now - timedelta(hours=36))

    assert bank.connection_status == "healthy"
    assert bank.cash_total_brl == -125.50
    assert bank.credit_balance_brl == 7800
    assert bank.investments_total_brl == 22_000_000
    assert [row.name for row in bank.investments] == ["BILLFISH FIA"]
    assert [row.id for row in bank.transactions] == ["recent"]
    assert bank.accounts[0].display_number == "•••• 34-5"


def test_manual_refresh_refusal_reports_scheduled_auto_sync() -> None:
    service = OpenFinanceService(Settings())
    now = datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc)
    next_sync = now + timedelta(hours=1)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        return httpx.Response(400, json={"message": "MeuPluggy item cant be updated"})

    with httpx.Client(base_url="https://api.pluggy.ai", transport=httpx.MockTransport(handler)) as client:
        status, detail = service._refresh_item(
            client,
            {
                "id": "item-1",
                "status": "UPDATED",
                "lastUpdatedAt": (now - timedelta(hours=2)).isoformat(),
                "nextAutoSyncAt": next_sync.isoformat(),
            },
            True,
            now,
        )

        assert status == "scheduled"
        assert "13:00" in detail


def test_integration_health_separates_pluggy_and_each_bank() -> None:
    service = OpenFinanceService(Settings(pluggy_item_ids="btg,santander,itau"))
    now = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)
    items = [
        ("btg", {"status": "UPDATED", "executionStatus": "SUCCESS", "lastUpdatedAt": now.isoformat(), "connector": {"name": "MeuPluggy", "isOpenFinance": True}}),
        ("santander", {"status": "WAITING_USER_INPUT", "executionStatus": "ERROR", "lastUpdatedAt": now.isoformat(), "connector": {"name": "MeuPluggy", "isOpenFinance": True}}),
        ("itau", {"status": "UPDATED", "executionStatus": "SUCCESS", "lastUpdatedAt": now.isoformat(), "connector": {"name": "MeuPluggy", "isOpenFinance": True}}),
    ]

    health = {item.name: item for item in service._build_integration_health(items, [], now, authenticated=True)}

    assert health["Pluggy API"].status == "healthy"
    assert health["BTG Pactual"].status == "healthy"
    assert health["Santander"].status == "attention"
    assert health["Itaú"].status == "healthy"
    assert "Open Finance" in health["BTG Pactual"].detail
