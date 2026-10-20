"""Synthetic CVM open-data archives (ITR/DFP) in the real file layout. No real issuer, no real figure."""
from __future__ import annotations

import io
import zipfile
from typing import Any

FLOW_HEADER = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;"
    "ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA"
)
POINT_HEADER = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;"
    "ORDEM_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA"
)
INDEX_HEADER = "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC"
CAPITAL_HEADER = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;QT_ACAO_ORDIN_CAP_INTEGR;QT_ACAO_PREF_CAP_INTEGR;"
    "QT_ACAO_TOTAL_CAP_INTEGR;QT_ACAO_ORDIN_TESOURO;QT_ACAO_PREF_TESOURO;QT_ACAO_TOTAL_TESOURO"
)

INDUSTRY = {"tax_id": "11.111.111/0001-11", "name": "INDUSTRIA SINTETICA S.A.", "code": "90001"}
SERVICES = {"tax_id": "22.222.222/0001-22", "name": "SERVICOS SINTETICOS S.A.", "code": "90002"}
BANK = {"tax_id": "33.333.333/0001-33", "name": "BANCO SINTETICO S.A.", "code": "90003"}

# Standalone quarters in BRL thousands, (year offset from the current year, quarter):
# revenue, EBIT, D&A, net income to controllers, minority share of net income, CFO, PP&E capex, intangible capex
QUARTERS = {
    (-1, 1): (100, 20, 5, 10, 1, 15, -4, -2),
    (-1, 2): (110, 22, 5, 11, 1, 16, -5, -2),
    (-1, 3): (120, 24, 6, 12, 1, 17, -5, -3),
    (-1, 4): (130, 26, 6, 13, 1, 18, -6, -3),
    (0, 1): (140, 28, 7, 14, 1, 19, -7, -3),
    (0, 2): (150, 30, 7, 15, 1, 20, -8, -3),
}
QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
STANDALONE_START = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}


def _ytd(year_offset: int, quarter: int) -> tuple[int, ...]:
    rows = [QUARTERS[(year_offset, q)] for q in range(1, quarter + 1)]
    return tuple(sum(values) for values in zip(*rows))


def _flow(company: dict[str, str], refer: str, version: int, order: str, start: str, end: str,
          accounts: list[tuple[str, str, float]], *, scale: str = "MIL") -> list[str]:
    return [
        f"{company['tax_id']};{refer};{version};{company['name']};{company['code']};DF;REAL;{scale};"
        f"{order};{start};{end};{code};{description};{value};S"
        for code, description, value in accounts
    ]


def _point(company: dict[str, str], refer: str, version: int, order: str, end: str,
           accounts: list[tuple[str, str, float]]) -> list[str]:
    return [
        f"{company['tax_id']};{refer};{version};{company['name']};{company['code']};DF;REAL;MIL;"
        f"{order};{end};{code};{description};{value};S"
        for code, description, value in accounts
    ]


def industry_income(values: tuple[int, ...], *, individual: bool = False) -> list[tuple[str, str, float]]:
    revenue, ebit, _, net, minority, *_ = values
    rows = [
        ("3.01", "Receita de Venda de Bens e/ou Serviços", revenue),
        ("3.02", "Custo dos Bens e/ou Serviços Vendidos", -revenue * 0.6),
        ("3.03", "Resultado Bruto", revenue * 0.4),
        ("3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", ebit),
        ("3.06", "Resultado Financeiro", -4),
        ("3.07", "Resultado Antes dos Tributos sobre o Lucro", ebit - 4),
        ("3.08", "Imposto de Renda e Contribuição Social sobre o Lucro", net + minority - (ebit - 4)),
        ("3.99.01.01", "ON", 0.1),
    ]
    if individual:
        rows.append(("3.11", "Lucro/Prejuízo do Período", net))
    else:
        rows.extend([
            ("3.11", "Lucro/Prejuízo Consolidado do Período", net + minority),
            ("3.11.01", "Atribuído a Sócios da Empresa Controladora", net),
            ("3.11.02", "Atribuído a Sócios Não Controladores", minority),
        ])
    return rows


def industry_value_added(values: tuple[int, ...]) -> list[tuple[str, str, float]]:
    amortization = values[2]
    return [
        ("7.04", "Retenções", -amortization),
        ("7.04.01", "Depreciação, Amortização e Exaustão", -amortization),
        ("7.04.02", "Outras", 0),
    ]


def industry_cash_flow(values: tuple[int, ...]) -> list[tuple[str, str, float]]:
    operating, ppe, intangible = values[5], values[6], values[7]
    return [
        ("6.01", "Caixa Líquido Atividades Operacionais", operating),
        ("6.01.01.02", "Depreciação e amortização", values[2]),
        ("6.02", "Caixa Líquido Atividades de Investimento", ppe + intangible + 1),
        ("6.02.01", "Aquisição de imobilizado", ppe),
        ("6.02.02", "Aquisição de intangível", intangible),
        ("6.02.03", "Venda de imobilizado", 1),
        ("6.02.04", "Aplicações financeiras", -50),
    ]


def industry_balance(cash: float) -> tuple[list[tuple[str, str, float]], list[tuple[str, str, float]]]:
    assets = [
        ("1", "Ativo Total", 1_000),
        ("1.01", "Ativo Circulante", 300),
        ("1.01.01", "Caixa e Equivalentes de Caixa", cash),
        ("1.01.02", "Aplicações Financeiras", 30),
    ]
    liabilities = [
        ("2", "Passivo Total", 1_000),
        ("2.01.04", "Empréstimos e Financiamentos", 20),
        ("2.02.01", "Empréstimos e Financiamentos", 80),
        ("2.03", "Patrimônio Líquido Consolidado", 500),
        ("2.03.09", "Participação dos Acionistas Não Controladores", 25),
    ]
    return assets, liabilities


class Package:
    def __init__(self, document_type: str, year: int) -> None:
        self.document_type = document_type
        self.year = year
        self.files: dict[str, list[str]] = {}
        self.index: list[dict[str, str]] = []

    def add(self, statement: str, scope: str, rows: list[str]) -> None:
        name = f"{self.document_type}_cia_aberta_{statement}_{scope}_{self.year}.csv"
        self.files.setdefault(name, []).extend(rows)

    def document(self, company: dict[str, str], refer: str, version: int, received: str) -> None:
        self.index.append({
            "CNPJ_CIA": company["tax_id"], "DT_REFER": refer, "VERSAO": str(version),
            "DENOM_CIA": company["name"], "CD_CVM": company["code"], "CATEG_DOC": self.document_type.upper(),
            "ID_DOC": f"{self.document_type}-{company['code']}-{refer}-{version}", "DT_RECEB": received,
            "LINK_DOC": f"https://example.invalid/{self.document_type}/{company['code']}/{refer}",
        })

    def capital(self, company: dict[str, str], refer: str, version: int, total: int, treasury: int) -> None:
        name = f"{self.document_type}_cia_aberta_composicao_capital_{self.year}.csv"
        self.files.setdefault(name, []).append(
            f"{company['tax_id']};{refer};{version};{company['name']};{total};0;{total};{treasury};0;{treasury}"
        )

    def payload(self) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            index_rows = [INDEX_HEADER] + [";".join(row[column] for column in INDEX_HEADER.split(";")) for row in self.index]
            archive.writestr(f"{self.document_type}_cia_aberta_{self.year}.csv", ("\n".join(index_rows) + "\n").encode("latin-1"))
            for name, rows in self.files.items():
                if "composicao_capital" in name:
                    header = CAPITAL_HEADER
                elif "_BPA_" in name or "_BPP_" in name:
                    header = POINT_HEADER
                else:
                    header = FLOW_HEADER
                archive.writestr(name, ("\n".join([header, *rows]) + "\n").encode("latin-1"))
        return buffer.getvalue()


def build_packages(year: int) -> dict[tuple[str, int], Package]:
    """ITR of ``year`` (Q1, Q2) and ``year - 1`` (Q1-Q3), DFP of ``year - 1``.

    The industrial issuer files consolidated and individual statements (individual figures doubled, so a leak shows);
    the services issuer files only individual statements; the bank files a financial-institution layout. The Q2 ITR
    comparative of last year's first half is restated (revenue +5): the as-filed own document must win."""
    previous = year - 1
    itr = Package("itr", year)
    itr_previous = Package("itr", previous)
    dfp_previous = Package("dfp", previous)

    for quarter in (1, 2, 3):
        refer = f"{previous}-{QUARTER_END[quarter]}"
        values = _ytd(-1, quarter)
        start = f"{previous}-01-01"
        itr_previous.document(INDUSTRY, refer, 1, f"{previous}-{quarter * 3 + 1:02d}-10")
        itr_previous.add("DRE", "con", _flow(INDUSTRY, refer, 1, "ÚLTIMO", start, refer, industry_income(values)))
        itr_previous.add("DVA", "con", _flow(INDUSTRY, refer, 1, "ÚLTIMO", start, refer, industry_value_added(values)))
        itr_previous.add("DFC_MI", "con", _flow(INDUSTRY, refer, 1, "ÚLTIMO", start, refer, industry_cash_flow(values)))
        assets, liabilities = industry_balance(40 + quarter)
        itr_previous.add("BPA", "con", _point(INDUSTRY, refer, 1, "ÚLTIMO", refer, assets))
        itr_previous.add("BPP", "con", _point(INDUSTRY, refer, 1, "ÚLTIMO", refer, liabilities))
        itr_previous.capital(INDUSTRY, refer, 1, 1_000, 10)

    refer = f"{previous}-12-31"
    values = _ytd(-1, 4)
    start = f"{previous}-01-01"
    dfp_previous.document(INDUSTRY, refer, 1, f"{year}-03-20")
    dfp_previous.add("DRE", "con", _flow(INDUSTRY, refer, 1, "ÚLTIMO", start, refer, industry_income(values)))
    dfp_previous.add("DVA", "con", _flow(INDUSTRY, refer, 1, "ÚLTIMO", start, refer, industry_value_added(values)))
    dfp_previous.add("DFC_MI", "con", _flow(INDUSTRY, refer, 1, "ÚLTIMO", start, refer, industry_cash_flow(values)))
    assets, liabilities = industry_balance(45)
    dfp_previous.add("BPA", "con", _point(INDUSTRY, refer, 1, "ÚLTIMO", refer, assets))
    dfp_previous.add("BPP", "con", _point(INDUSTRY, refer, 1, "ÚLTIMO", refer, liabilities))
    dfp_previous.capital(INDUSTRY, refer, 1, 1_000, 10)

    for quarter in (1, 2):
        refer = f"{year}-{QUARTER_END[quarter]}"
        values = _ytd(0, quarter)
        comparative = _ytd(-1, quarter)
        if quarter == 2:
            comparative = (comparative[0] + 5, *comparative[1:])
        start = f"{year}-01-01"
        version = 2 if quarter == 2 else 1
        itr.document(INDUSTRY, refer, 1, f"{year}-{quarter * 3 + 1:02d}-10")
        if version == 2:
            itr.document(INDUSTRY, refer, 2, f"{year}-{quarter * 3 + 2:02d}-02")
        itr.add("DRE", "con", _flow(INDUSTRY, refer, version, "ÚLTIMO", start, refer, industry_income(values)))
        itr.add("DRE", "con", _flow(
            INDUSTRY, refer, version, "PENÚLTIMO", f"{previous}-01-01", f"{previous}-{QUARTER_END[quarter]}",
            industry_income(comparative),
        ))
        itr.add("DVA", "con", _flow(INDUSTRY, refer, version, "ÚLTIMO", start, refer, industry_value_added(values)))
        itr.add("DFC_MI", "con", _flow(INDUSTRY, refer, version, "ÚLTIMO", start, refer, industry_cash_flow(values)))
        assets, liabilities = industry_balance(50 + quarter)
        itr.add("BPA", "con", _point(INDUSTRY, refer, version, "ÚLTIMO", refer, assets))
        itr.add("BPP", "con", _point(INDUSTRY, refer, version, "ÚLTIMO", refer, liabilities))
        itr.capital(INDUSTRY, refer, version, 1_000, 10)
        doubled = tuple(value * 2 for value in values)
        itr.add("DRE", "ind", _flow(INDUSTRY, refer, version, "ÚLTIMO", start, refer, industry_income(doubled, individual=True)))

        itr.document(SERVICES, refer, 1, f"{year}-{quarter * 3 + 1:02d}-12")
        itr.add("DRE", "ind", _flow(SERVICES, refer, 1, "ÚLTIMO", start, refer, industry_income(values, individual=True)))
        itr.add("DVA", "ind", _flow(SERVICES, refer, 1, "ÚLTIMO", start, refer, industry_value_added(values)))
        services_assets, services_liabilities = industry_balance(10)
        itr.add("BPA", "ind", _point(SERVICES, refer, 1, "ÚLTIMO", refer, services_assets))
        itr.add("BPP", "ind", _point(SERVICES, refer, 1, "ÚLTIMO", refer, [
            (code, description.replace(" Consolidado", ""), value)
            for code, description, value in services_liabilities if code != "2.03.09"
        ]))

        itr.document(BANK, refer, 1, f"{year}-{quarter * 3 + 1:02d}-15")
        itr.add("DRE", "con", _flow(BANK, refer, 1, "ÚLTIMO", start, refer, [
            ("3.01", "Receitas da Intermediação Financeira", 900 * quarter),
            ("3.03", "Resultado Bruto Intermediação Financeira", 300 * quarter),
            ("3.05", "Resultado Antes dos Tributos sobre o Lucro", 120 * quarter),
            ("3.06", "Imposto de Renda e Contribuição Social sobre o Lucro", -40 * quarter),
            ("3.09", "Lucro/Prejuízo Consolidado do Período", 80 * quarter),
            ("3.09.01", "Atribuído a Sócios da Empresa Controladora", 78 * quarter),
        ]))
        itr.add("DVA", "con", _flow(BANK, refer, 1, "ÚLTIMO", start, refer, [
            ("7.04.01", "Depreciação, Amortização e Exaustão", -9 * quarter),
        ]))
        itr.add("BPP", "con", _point(BANK, refer, 1, "ÚLTIMO", refer, [
            ("2.02.01", "Depósitos", 5_000),
            ("2.03", "Provisões", 70),
            ("2.07", "Patrimônio Líquido Consolidado", 800),
        ]))
    return {("itr", year): itr, ("itr", previous): itr_previous, ("dfp", previous): dfp_previous}


ISSUERS: dict[str, dict[str, Any]] = {
    INDUSTRY["tax_id"]: {"symbols": ["INDS3", "INDS4"], "company_name": INDUSTRY["name"], "regulator_id": INDUSTRY["code"]},
    SERVICES["tax_id"]: {"symbols": ["SERV3"], "company_name": SERVICES["name"], "regulator_id": SERVICES["code"]},
    BANK["tax_id"]: {"symbols": ["BSIN3"], "company_name": BANK["name"], "regulator_id": BANK["code"]},
}
