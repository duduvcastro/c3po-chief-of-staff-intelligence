from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .schemas import (
    IntegrationHealth,
    OpenFinanceAccount,
    OpenFinanceBank,
    OpenFinanceInvestment,
    OpenFinanceResponse,
    OpenFinanceTransaction,
)


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
BANK_ORDER = ("btg", "santander", "itau")
BANK_NAMES = {"btg": "BTG Pactual", "santander": "Santander", "itau": "Itaú"}


class PluggyRequestError(RuntimeError):
    pass


class OpenFinanceService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def snapshot(self, *, hours: int = 36, refresh: bool = True) -> OpenFinanceResponse:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=hours)
        if not self.settings.pluggy_client_id or not self.settings.pluggy_client_secret:
            raise PluggyRequestError("Credenciais do Pluggy não estão configuradas.")
        if not self.settings.pluggy_items:
            raise PluggyRequestError("Nenhuma conexão do Pluggy foi configurada.")

        errors: list[str] = []
        with httpx.Client(
            base_url=self.settings.pluggy_base_url.rstrip("/"),
            timeout=self.settings.pluggy_timeout_seconds,
            headers={"Accept": "application/json", "User-Agent": "C3PO-Chief-of-Staff/1.0"},
        ) as client:
            api_key = self._authenticate(client)
            client.headers["X-API-KEY"] = api_key
            item_payloads = []
            for item_id in self.settings.pluggy_items:
                try:
                    item = self._get_json(client, f"/items/{item_id}")
                    refresh_status, refresh_detail = self._refresh_item(client, item, refresh, now)
                    if refresh_status == "started":
                        item = self._wait_for_item(client, item_id, item)
                        if str(item.get("status") or "").upper() == "UPDATED":
                            refresh_status = "completed"
                            refresh_detail = "Sincronização concluída nesta consulta."
                        else:
                            refresh_detail = "Sincronização iniciada; os dados anteriores permanecem visíveis até a conclusão."
                    item_payloads.append((item_id, item, refresh_status, refresh_detail))
                except Exception as exc:
                    errors.append(f"Conexão {item_id[:8]}: {self._safe_error(exc)}")

            grouped: dict[str, dict[str, Any]] = {
                code: {"items": [], "accounts": [], "investments": [], "transactions": [], "errors": []}
                for code in BANK_ORDER
            }
            for item_id, item, refresh_status, refresh_detail in item_payloads:
                try:
                    accounts = self._get_all(client, "/accounts", {"itemId": item_id})
                except Exception as exc:
                    accounts = []
                    errors.append(f"Contas {item_id[:8]}: {self._safe_error(exc)}")
                try:
                    investments = self._get_all(client, "/investments", {"itemId": item_id})
                except Exception as exc:
                    investments = []
                    errors.append(f"Investimentos {item_id[:8]}: {self._safe_error(exc)}")
                bank_code = self._detect_bank(item, accounts, investments)
                if bank_code not in grouped:
                    errors.append(f"Conexão {item_id[:8]} não corresponde a BTG, Santander ou Itaú.")
                    continue
                bucket = grouped[bank_code]
                bucket["items"].append((item, refresh_status, refresh_detail))
                bucket["accounts"].extend(accounts)
                bucket["investments"].extend(investments)

                for account in accounts:
                    account_id = str(account.get("id") or "")
                    if not account_id:
                        continue
                    try:
                        transactions = self._get_cursor_all(
                            client,
                            "/v2/transactions",
                            {
                                "accountId": account_id,
                                "dateFrom": window_start.date().isoformat(),
                                "dateTo": now.date().isoformat(),
                            },
                        )
                        for transaction in transactions:
                            transaction["_account"] = account
                        bucket["transactions"].extend(transactions)
                    except Exception as exc:
                        message = f"Extrato {BANK_NAMES[bank_code]} {self._masked_number(account)}: {self._safe_error(exc)}"
                        bucket["errors"].append(message)
                        errors.append(message)

        banks = [self._build_bank(code, grouped[code], window_start) for code in BANK_ORDER]
        return OpenFinanceResponse(
            generated_at=now,
            window_hours=hours,
            window_start=window_start,
            source="Pluggy Open Finance",
            refresh_requested=refresh,
            banks=banks,
            cash_total_brl=sum(bank.cash_total_brl for bank in banks),
            credit_balance_brl=sum(bank.credit_balance_brl for bank in banks),
            investments_total_brl=sum(bank.investments_total_brl for bank in banks),
            errors=errors,
            methodology={
                "refresh": "A aba relê o Pluggy em cada abertura. Quando o conector permite, solicita uma nova sincronização; caso contrário, exibe o próximo auto-sync informado pela Pluggy.",
                "window": f"Movimentações filtradas pela data e hora efetiva das últimas {hours} horas.",
                "privacy": "Números de conta são mascarados; credenciais e chaves nunca são enviadas ao navegador.",
                "totals": "Totais consolidados incluem apenas posições denominadas em BRL; faturas de cartão são separadas do caixa.",
            },
        )

    def integration_health(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> list[IntegrationHealth]:
        now = datetime.now(timezone.utc)
        if not self.settings.pluggy_client_id or not self.settings.pluggy_client_secret:
            return self._build_integration_health([], ["Credenciais do Pluggy não configuradas."], now, authenticated=False)
        if not self.settings.pluggy_items:
            return self._build_integration_health([], ["Nenhuma conexão do Pluggy configurada."], now, authenticated=False)

        items: list[tuple[str, dict[str, Any]]] = []
        errors: list[str] = []
        authenticated = False
        with httpx.Client(
            base_url=self.settings.pluggy_base_url.rstrip("/"),
            timeout=timeout_seconds or self.settings.pluggy_timeout_seconds,
            headers={"Accept": "application/json", "User-Agent": "C3PO-Chief-of-Staff/1.0"},
        ) as client:
            try:
                client.headers["X-API-KEY"] = self._authenticate(client)
                authenticated = True
            except Exception as exc:
                errors.append(self._safe_error(exc))
                return self._build_integration_health(items, errors, now, authenticated=False)

            for item_id in self.settings.pluggy_items:
                try:
                    item = self._get_json(client, f"/items/{item_id}")
                    accounts = self._get_all(client, "/accounts", {"itemId": item_id})
                    items.append((self._detect_bank(item, accounts, []), item))
                except Exception as exc:
                    errors.append(f"Conexão {item_id[:8]}: {self._safe_error(exc)}")

        return self._build_integration_health(items, errors, now, authenticated=authenticated)

    def _build_integration_health(
        self,
        items: list[tuple[str, dict[str, Any]]],
        errors: list[str],
        now: datetime,
        *,
        authenticated: bool,
    ) -> list[IntegrationHealth]:
        expected = len(self.settings.pluggy_items)
        read_count = len(items)
        if not authenticated:
            pluggy_status = "offline"
            pluggy_detail = errors[0] if errors else "Pluggy indisponível."
        elif errors or read_count < expected:
            pluggy_status = "attention"
            pluggy_detail = f"API autenticada · {read_count}/{expected} conexões lidas"
        else:
            pluggy_status = "healthy"
            pluggy_detail = f"API autenticada · {read_count}/{expected} conexões lidas"

        result = [
            IntegrationHealth(
                name="Pluggy API",
                status=pluggy_status,
                detail=pluggy_detail,
                last_update=now.astimezone(SAO_PAULO).strftime("%d/%m %H:%M"),
            )
        ]
        for bank_code in BANK_ORDER:
            bank_items = [item for detected_code, item in items if detected_code == bank_code]
            if not bank_items:
                result.append(
                    IntegrationHealth(
                        name=BANK_NAMES[bank_code],
                        status="offline",
                        detail="Nenhuma conexão identificada no Pluggy.",
                        last_update="Sem sincronização",
                    )
                )
                continue

            raw_statuses = {str(item.get("status") or "").upper() for item in bank_items}
            execution_statuses = {str(item.get("executionStatus") or "").upper() for item in bank_items}
            connectors = [item.get("connector") for item in bank_items if isinstance(item.get("connector"), dict)]
            connector_names = sorted({str(item.get("name") or "").strip() for item in connectors if item.get("name")})
            connector_label = ", ".join(connector_names) or "Pluggy"
            open_finance = bool(connectors) and all(bool(item.get("isOpenFinance")) for item in connectors)

            if raw_statuses & {"WAITING_USER_INPUT", "LOGIN_ERROR", "OUTDATED", "UPDATE_ERROR"}:
                bank_status = "attention"
                state_label = "reautenticação necessária"
            elif "UPDATING" in raw_statuses or "CREATED" in raw_statuses:
                bank_status = "attention"
                state_label = "sincronização em andamento"
            elif raw_statuses == {"UPDATED"} and not execution_statuses & {"ERROR", "PARTIAL_SUCCESS"}:
                bank_status = "healthy"
                state_label = "sincronizado"
            else:
                bank_status = "attention"
                state_label = "status em revisão"

            last_sync_values = [self._parse_datetime(item.get("lastUpdatedAt")) for item in bank_items]
            last_sync_at = max((value for value in last_sync_values if value), default=None)
            result.append(
                IntegrationHealth(
                    name=BANK_NAMES[bank_code],
                    status=bank_status,
                    detail=f"{'Open Finance' if open_finance else 'Pluggy'} · {state_label} · {connector_label}",
                    last_update=last_sync_at.astimezone(SAO_PAULO).strftime("%d/%m %H:%M") if last_sync_at else "Sem sincronização",
                )
            )
        return result

    def _authenticate(self, client: httpx.Client) -> str:
        response = client.post(
            "/auth",
            json={"clientId": self.settings.pluggy_client_id, "clientSecret": self.settings.pluggy_client_secret},
        )
        self._raise_for_status(response, "autenticação")
        api_key = response.json().get("apiKey")
        if not api_key:
            raise PluggyRequestError("O Pluggy não retornou uma chave de sessão.")
        return str(api_key)

    def _refresh_item(
        self,
        client: httpx.Client,
        item: dict[str, Any],
        refresh: bool,
        now: datetime,
    ) -> tuple[str, str]:
        status = str(item.get("status") or "").upper()
        if status in {"WAITING_USER_INPUT", "LOGIN_ERROR"}:
            return "needs_action", "A conexão precisa ser revalidada no Pluggy."
        if status == "UPDATING":
            return "started", "O Pluggy já está sincronizando esta conexão."
        last_updated = self._parse_datetime(item.get("lastUpdatedAt"))
        age_minutes = (now - last_updated).total_seconds() / 60 if last_updated else float("inf")
        if not refresh or age_minutes < self.settings.pluggy_refresh_minimum_minutes:
            detail = "Dados relidos agora; sincronização bancária recente."
            return "recent", detail
        item_id = str(item.get("id") or "")
        try:
            response = client.patch(f"/items/{item_id}", json={})
            if response.status_code in {400, 409, 429}:
                payload = self._json_or_empty(response)
                message = self._response_message(payload)
                if "credential" in message.lower() or "mfa" in message.lower() or "input" in message.lower():
                    return "needs_action", "A instituição exige nova autenticação no Pluggy."
                next_sync = self._parse_datetime(item.get("nextAutoSyncAt"))
                if next_sync:
                    return "scheduled", f"Atualização manual indisponível; próximo auto-sync previsto para {self._local_time(next_sync)}."
                return "unavailable", f"A Pluggy recusou a atualização manual{f': {message}' if message else '.'}"
            self._raise_for_status(response, "atualização da conexão")
            return "started", "Sincronização solicitada ao banco."
        except PluggyRequestError:
            return "unavailable", "Não foi possível solicitar nova sincronização; exibindo o último dado disponível."

    def _wait_for_item(self, client: httpx.Client, item_id: str, fallback: dict[str, Any]) -> dict[str, Any]:
        latest = fallback
        for _ in range(2):
            time.sleep(1.0)
            try:
                latest = self._get_json(client, f"/items/{item_id}")
            except PluggyRequestError:
                break
            if str(latest.get("status") or "").upper() not in {"UPDATING", "CREATED"}:
                break
        return latest

    def _get_json(self, client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = client.get(path, params=params)
        self._raise_for_status(response, path)
        payload = response.json()
        return payload if isinstance(payload, dict) else {"results": payload}

    def _get_all(self, client: httpx.Client, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while page <= 10:
            payload = self._get_json(client, path, {**params, "page": page, "pageSize": 200})
            page_rows = self._results(payload)
            rows.extend(page_rows)
            total_pages = int(payload.get("totalPages") or payload.get("total_pages") or 0)
            if (total_pages and page >= total_pages) or len(page_rows) < 200:
                break
            page += 1
        return rows

    def _get_cursor_all(self, client: httpx.Client, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        next_path = path
        next_params: dict[str, Any] | None = params
        for _ in range(10):
            payload = self._get_json(client, next_path, next_params)
            rows.extend(self._results(payload))
            next_url = payload.get("next")
            if not next_url:
                break
            next_path = urljoin(self.settings.pluggy_base_url.rstrip("/") + "/", str(next_url))
            next_params = None
        return rows

    def _build_bank(self, code: str, bucket: dict[str, Any], window_start: datetime) -> OpenFinanceBank:
        accounts = [self._account(row) for row in bucket["accounts"]]
        investments = [self._investment(row) for row in bucket["investments"]]
        investments = [row for row in investments if row.gross_value > 0 or (row.net_value or 0) > 0]
        transactions = []
        for row in bucket["transactions"]:
            transaction_at = self._parse_datetime(row.get("date") or row.get("postedDate"))
            if transaction_at is None or transaction_at < window_start:
                continue
            transactions.append(self._transaction(row, transaction_at))
        transactions.sort(key=lambda row: row.transaction_at, reverse=True)

        item_rows = bucket["items"]
        item = item_rows[0][0] if item_rows else {}
        raw_statuses = {str(row[0].get("status") or "").upper() for row in item_rows}
        execution_status = ", ".join(sorted({str(row[0].get("executionStatus") or "-") for row in item_rows})) or "-"
        if not item_rows:
            connection_status = "offline"
            refresh_status = "unavailable"
            refresh_detail = "Nenhuma conexão configurada para esta instituição."
        elif "WAITING_USER_INPUT" in raw_statuses or "LOGIN_ERROR" in raw_statuses or "OUTDATED" in raw_statuses:
            connection_status = "attention"
            refresh_status = "needs_action"
            refresh_detail = "A conexão precisa ser revisada no painel do Pluggy."
        elif "UPDATING" in raw_statuses:
            connection_status = "syncing"
            refresh_status = "started"
            refresh_detail = "Sincronização em andamento."
        else:
            connection_status = "healthy"
            refresh_status = item_rows[0][1]
            refresh_detail = item_rows[0][2]

        last_sync_values = [self._parse_datetime(row[0].get("lastUpdatedAt")) for row in item_rows]
        last_sync_at = max((value for value in last_sync_values if value), default=None)
        next_sync_values = [self._parse_datetime(row[0].get("nextAutoSyncAt")) for row in item_rows]
        next_sync_at = min((value for value in next_sync_values if value), default=None)
        connectors = [row[0].get("connector") for row in item_rows if isinstance(row[0].get("connector"), dict)]
        connector_names = sorted({str(row.get("name") or "").strip() for row in connectors if row.get("name")})
        return OpenFinanceBank(
            code=code,
            name=BANK_NAMES[code],
            connection_status=connection_status,
            execution_status=execution_status,
            last_sync_at=last_sync_at,
            next_sync_at=next_sync_at,
            connector_name=", ".join(connector_names) or None,
            is_open_finance=bool(connectors) and all(bool(row.get("isOpenFinance")) for row in connectors),
            refresh_status=refresh_status,
            refresh_detail=refresh_detail,
            accounts=accounts,
            investments=investments,
            transactions=transactions,
            cash_total_brl=sum(row.balance for row in accounts if row.product == "BANK" and row.currency == "BRL"),
            credit_balance_brl=sum(row.balance for row in accounts if row.product == "CREDIT" and row.currency == "BRL"),
            investments_total_brl=sum(row.gross_value for row in investments if row.currency == "BRL"),
        )

    @staticmethod
    def _local_time(value: datetime) -> str:
        return value.astimezone(SAO_PAULO).strftime("%d/%m às %H:%M")

    def _account(self, row: dict[str, Any]) -> OpenFinanceAccount:
        product = str(row.get("type") or "OTHER").upper()
        if product not in {"BANK", "CREDIT"}:
            product = "OTHER"
        credit = row.get("creditData") if isinstance(row.get("creditData"), dict) else {}
        return OpenFinanceAccount(
            id=str(row.get("id") or ""),
            name=str(row.get("name") or row.get("marketingName") or "Conta").strip(),
            product=product,
            subtype=str(row.get("subtype") or "-").upper(),
            display_number=self._masked_number(row),
            balance=self._amount(row.get("balance", row.get("currentBalance", row.get("availableBalance")))) or 0,
            currency=str(row.get("currencyCode") or row.get("currency") or "BRL").upper(),
            available_credit=self._amount(credit.get("availableCreditLimit")),
            credit_limit=self._amount(credit.get("creditLimit")),
            due_date=str(credit.get("balanceDueDate") or "")[:10] or None,
        )

    def _investment(self, row: dict[str, Any]) -> OpenFinanceInvestment:
        unit_value = self._amount(row.get("value"))
        quantity = self._amount(row.get("quantity"))
        gross_value = self._amount(row.get("amount"))
        if (gross_value is None or gross_value == 0) and unit_value is not None and quantity is not None:
            gross_value = unit_value * quantity
        net_value = self._amount(row.get("balance", row.get("netAmount")))
        if gross_value is None:
            gross_value = self._amount(row.get("grossAmount"))
        if gross_value is None:
            gross_value = net_value or 0
        return OpenFinanceInvestment(
            id=str(row.get("id") or ""),
            name=str(row.get("name") or row.get("code") or row.get("type") or "Investimento").strip(),
            type=str(row.get("type") or row.get("subtype") or "-").upper(),
            gross_value=gross_value,
            net_value=net_value,
            unit_value=unit_value,
            quantity=quantity,
            currency=str(row.get("currencyCode") or row.get("currency") or "BRL").upper(),
            status=str(row.get("status") or "ACTIVE").upper(),
            as_of=self._parse_datetime(row.get("date") or row.get("updatedAt")),
        )

    def _transaction(self, row: dict[str, Any], transaction_at: datetime) -> OpenFinanceTransaction:
        account = row.get("_account") or {}
        product = str(account.get("type") or "OTHER").upper()
        if product not in {"BANK", "CREDIT"}:
            product = "OTHER"
        return OpenFinanceTransaction(
            id=str(row.get("id") or ""),
            account_id=str(account.get("id") or ""),
            account_name=str(account.get("name") or account.get("marketingName") or "Conta").strip(),
            account_number=self._masked_number(account),
            account_product=product,
            description=str(row.get("description") or row.get("descriptionRaw") or row.get("merchantName") or "Movimentação").strip(),
            category=str(row.get("category") or "Outros").strip(),
            amount=self._amount(row.get("amount", row.get("value"))) or 0,
            currency=str(row.get("currencyCode") or row.get("currency") or "BRL").upper(),
            status=str(row.get("status") or "-").upper(),
            transaction_at=transaction_at,
        )

    @staticmethod
    def _detect_bank(item: dict[str, Any], accounts: list[dict[str, Any]], investments: list[dict[str, Any]]) -> str:
        connector = item.get("connector") if isinstance(item.get("connector"), dict) else {}
        names = [str(connector.get("name") or ""), str(item.get("name") or "")]
        names.extend(str(row.get("name") or row.get("marketingName") or "") for row in accounts)
        names.extend(str(row.get("name") or row.get("code") or "") for row in investments[:5])
        text = " ".join(names).lower()
        if "santander" in text or "aadvantage" in text:
            return "santander"
        if "itaú" in text or "itau" in text or "personnalite" in text:
            return "itau"
        if "btg" in text or "billfish" in text:
            return "btg"
        return "unknown"

    @staticmethod
    def _masked_number(row: dict[str, Any]) -> str:
        raw = str(row.get("number") or row.get("displayNumber") or "").strip()
        if not raw:
            return "••••"
        return f"•••• {raw[-4:]}"

    @staticmethod
    def _amount(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SAO_PAULO)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("results", "data", "items", "accounts", "transactions", "investments"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return []

    @staticmethod
    def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _response_message(cls, payload: dict[str, Any]) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "")
        return str(payload.get("message") or error or "")

    @classmethod
    def _raise_for_status(cls, response: httpx.Response, context: str) -> None:
        if response.is_success:
            return
        message = cls._response_message(cls._json_or_empty(response))
        raise PluggyRequestError(f"{context}: HTTP {response.status_code}{f' · {message}' if message else ''}")

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc).replace("\n", " ").strip()
        return message[:220] or type(exc).__name__
