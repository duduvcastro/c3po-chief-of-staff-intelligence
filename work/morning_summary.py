#!/usr/bin/env python3
import base64
import argparse
import csv
import datetime as dt
import email.message
import gzip
import html
import math
import os
import re
import smtplib
import socket
import ssl
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from zoneinfo import ZoneInfo


SERVICE = os.getenv("EXCHANGE_KEYCHAIN_SERVICE", "chief-of-staff-exchange")
ACCOUNT = os.getenv("EXCHANGE_USER", "eu@eduardocastro.com.br")
SERVER = os.getenv("EXCHANGE_SERVER", "east.EXCH025.serverdata.net")
TIMEZONE = ZoneInfo("America/Sao_Paulo")
EWS_URL = f"https://{SERVER}/EWS/Exchange.asmx"
OUT_DIR = Path("outputs")
MARKET_SYMBOLS = [
    ("S&P 500 Fut.", "ES=F"),
    ("Nasdaq Fut.", "NQ=F"),
    ("Nikkei", "^N225"),
    ("DAX", "^GDAXI"),
    ("Shanghai Composite", "000001.SS"),
    ("USD/BRL", "BRL=X"),
    ("EUR/BRL", "EURBRL=X"),
    ("GBP/BRL", "GBPBRL=X"),
    ("BTC", "BTC-USD"),
    ("Ethereum", "ETH-USD"),
    ("Solana", "SOL-USD"),
    ("Bonk", "BONK-USD"),
    ("Doge", "DOGE-USD"),
    ("AMZN", "AMZN"),
    ("AVGO", "AVGO"),
    ("VOO", "VOO"),
    ("TTWO", "TTWO"),
    ("SPCX", "SPCX"),
    ("KWEB", "KWEB"),
    ("MHVYF", "MHVYF"),
    ("UNIP6", "UNIP6.SA"),
    ("PRNR3", "PRNR3.SA"),
]

FORECAST_CHART_LOCATIONS = [
    {
        "label": "Rio de Janeiro - Leblon",
        "city": "Rio de Janeiro",
        "region": "RJ",
        "country": "Brasil",
        "lat": -22.9847,
        "lon": -43.2237,
    },
    {
        "label": "Sao Paulo - Campo Belo",
        "city": "Sao Paulo",
        "region": "SP",
        "country": "Brasil",
        "lat": -23.6260,
        "lon": -46.6694,
    },
]

FORECAST_SUMMARY_LOCATIONS = [
    {
        "label": "Miami",
        "city": "Miami",
        "region": "Florida",
        "country": "EUA",
        "lat": 25.7617,
        "lon": -80.1918,
    },
    {
        "label": "Los Suenos",
        "city": "Los Suenos",
        "region": "Puntarenas",
        "country": "Costa Rica",
        "lat": 9.6530,
        "lon": -84.6630,
    },
    {
        "label": "Salvador",
        "city": "Salvador",
        "region": "BA",
        "country": "Brasil",
        "lat": -12.9777,
        "lon": -38.5016,
    },
    {
        "label": "Boston",
        "city": "Boston",
        "region": "Massachusetts",
        "country": "EUA",
        "lat": 42.3601,
        "lon": -71.0589,
    },
]

NEWS_SOURCES = [
    (
        "Globo.com",
        [
            "https://g1.globo.com/dynamo/economia/rss2.xml",
            "https://g1.globo.com/dynamo/politica/rss2.xml",
        ],
    ),
    (
        "UOL",
        [
            "https://www1.folha.uol.com.br/mercado/rss091.xml",
            "https://www1.folha.uol.com.br/poder/rss091.xml",
            "https://www1.folha.uol.com.br/mundo/rss091.xml",
            "https://www1.folha.uol.com.br/tec/rss091.xml",
            "https://www.uol.com.br/rss.xml",
            "https://rss.uol.com.br/feed/noticias.xml",
            "https://rss.uol.com.br/feed/economia.xml",
            "http://rss.uol.com.br/feed/noticias.xml",
            "https://noticias.uol.com.br/ultimas/index.xml",
        ],
    ),
    (
        "Bloomberg",
        [
            "https://feeds.bloomberg.com/markets/news.rss",
            "https://feeds.bloomberg.com/economics/news.rss",
            "https://feeds.bloomberg.com/politics/news.rss",
            "https://news.google.com/rss/search?q=site%3Abloomberg.com%20when%3A24h%20markets&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=site%3Abloomberg.com%20when%3A24h%20stocks&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=site%3Abloomberg.com%20when%3A24h%20economy&hl=en-US&gl=US&ceid=US:en",
        ],
    ),
    (
        "CNBC",
        [
            "https://www.cnbc.com/id/100003114/device/rss/rss.html",
            "https://www.cnbc.com/id/10001147/device/rss/rss.html",
            "https://www.cnbc.com/id/100727362/device/rss/rss.html",
        ],
    ),
]

WORLD_CUP_STATIC_MATCHES = [
    {"date": "2026-06-16", "home": "France", "away": "Senegal", "group": "I", "stadium": "New York/New Jersey Stadium", "region": "New Jersey", "score": "3-1"},
    {"date": "2026-06-16", "home": "Iraq", "away": "Norway", "group": "I", "stadium": "Boston Stadium", "region": "Massachusetts", "score": "1-4"},
    {"date": "2026-06-16", "home": "Argentina", "away": "Algeria", "group": "J", "stadium": "Kansas City Stadium", "region": "Missouri", "score": "3-0"},
    {"date": "2026-06-16", "home": "Austria", "away": "Jordan", "group": "J", "stadium": "San Francisco Bay Area Stadium", "region": "California", "score": "3-1"},
    {"date": "2026-06-17", "home": "Portugal", "away": "Congo DR", "group": "K", "stadium": "Houston Stadium", "region": "Texas", "kickoff_utc": "2026-06-17T17:00:00+00:00"},
    {"date": "2026-06-17", "home": "England", "away": "Croatia", "group": "L", "stadium": "Dallas Stadium", "region": "Texas", "kickoff_utc": "2026-06-17T20:00:00+00:00"},
    {"date": "2026-06-17", "home": "Ghana", "away": "Panama", "group": "L", "stadium": "Toronto Stadium", "region": "Ontario", "kickoff_utc": "2026-06-17T23:00:00+00:00"},
    {"date": "2026-06-17", "home": "Uzbekistan", "away": "Colombia", "group": "K", "stadium": "Mexico City Stadium", "region": "Mexico City", "kickoff_utc": "2026-06-18T02:00:00+00:00"},
    {"date": "2026-06-18", "home": "Czechia", "away": "South Africa", "group": "A", "stadium": "Atlanta Stadium", "region": "Georgia"},
    {"date": "2026-06-18", "home": "Switzerland", "away": "Bosnia and Herzegovina", "group": "B", "stadium": "Los Angeles Stadium", "region": "California"},
    {"date": "2026-06-18", "home": "Canada", "away": "Qatar", "group": "B", "stadium": "BC Place Vancouver", "region": "British Columbia"},
    {"date": "2026-06-18", "home": "Mexico", "away": "Korea Republic", "group": "A", "stadium": "Estadio Guadalajara", "region": "Jalisco"},
    {"date": "2026-06-19", "home": "Brazil", "away": "Haiti", "group": "C", "stadium": "Philadelphia Stadium", "region": "Pennsylvania"},
    {"date": "2026-06-19", "home": "Scotland", "away": "Morocco", "group": "C", "stadium": "Boston Stadium", "region": "Massachusetts"},
    {"date": "2026-06-19", "home": "Turkiye", "away": "Paraguay", "group": "D", "stadium": "San Francisco Bay Area Stadium", "region": "California"},
    {"date": "2026-06-19", "home": "USA", "away": "Australia", "group": "D", "stadium": "Seattle Stadium", "region": "Washington"},
    {"date": "2026-06-20", "home": "Germany", "away": "Cote d'Ivoire", "group": "E", "stadium": "Toronto Stadium", "region": "Ontario"},
    {"date": "2026-06-20", "home": "Ecuador", "away": "Curacao", "group": "E", "stadium": "Kansas City Stadium", "region": "Missouri"},
    {"date": "2026-06-20", "home": "Netherlands", "away": "Sweden", "group": "F", "stadium": "Houston Stadium", "region": "Texas"},
    {"date": "2026-06-20", "home": "Tunisia", "away": "Japan", "group": "F", "stadium": "Estadio Monterrey", "region": "Nuevo Leon"},
    {"date": "2026-06-21", "home": "Uruguay", "away": "Cabo Verde", "group": "H", "stadium": "Miami Stadium", "region": "Florida"},
    {"date": "2026-06-21", "home": "Spain", "away": "Saudi Arabia", "group": "H", "stadium": "Atlanta Stadium", "region": "Georgia"},
    {"date": "2026-06-21", "home": "Belgium", "away": "IR Iran", "group": "G", "stadium": "Los Angeles Stadium", "region": "California"},
    {"date": "2026-06-21", "home": "New Zealand", "away": "Egypt", "group": "G", "stadium": "BC Place Vancouver", "region": "British Columbia"},
    {"date": "2026-06-22", "home": "Norway", "away": "Senegal", "group": "I", "stadium": "New York/New Jersey Stadium", "region": "New Jersey"},
    {"date": "2026-06-22", "home": "France", "away": "Iraq", "group": "I", "stadium": "Philadelphia Stadium", "region": "Pennsylvania"},
    {"date": "2026-06-22", "home": "Argentina", "away": "Austria", "group": "J", "stadium": "Dallas Stadium", "region": "Texas"},
    {"date": "2026-06-22", "home": "Jordan", "away": "Algeria", "group": "J", "stadium": "San Francisco Bay Area Stadium", "region": "California"},
    {"date": "2026-06-23", "home": "England", "away": "Ghana", "group": "L", "stadium": "Boston Stadium", "region": "Massachusetts"},
    {"date": "2026-06-23", "home": "Panama", "away": "Croatia", "group": "L", "stadium": "Toronto Stadium", "region": "Ontario"},
    {"date": "2026-06-23", "home": "Portugal", "away": "Uzbekistan", "group": "K", "stadium": "Houston Stadium", "region": "Texas"},
    {"date": "2026-06-23", "home": "Colombia", "away": "Congo DR", "group": "K", "stadium": "Estadio Guadalajara", "region": "Jalisco"},
    {"date": "2026-06-24", "home": "Scotland", "away": "Brazil", "group": "C", "stadium": "Miami Stadium", "region": "Florida"},
    {"date": "2026-06-24", "home": "Morocco", "away": "Haiti", "group": "C", "stadium": "Atlanta Stadium", "region": "Georgia"},
    {"date": "2026-06-24", "home": "Switzerland", "away": "Canada", "group": "B", "stadium": "BC Place Vancouver", "region": "British Columbia"},
    {"date": "2026-06-24", "home": "Bosnia and Herzegovina", "away": "Qatar", "group": "B", "stadium": "Seattle Stadium", "region": "Washington"},
    {"date": "2026-06-24", "home": "Czechia", "away": "Mexico", "group": "A", "stadium": "Mexico City Stadium", "region": "Mexico City"},
    {"date": "2026-06-24", "home": "South Africa", "away": "Korea Republic", "group": "A", "stadium": "Estadio Monterrey", "region": "Nuevo Leon"},
    {"date": "2026-06-25", "home": "Curacao", "away": "Cote d'Ivoire", "group": "E", "stadium": "Philadelphia Stadium", "region": "Pennsylvania"},
    {"date": "2026-06-25", "home": "Ecuador", "away": "Germany", "group": "E", "stadium": "New York/New Jersey Stadium", "region": "New Jersey"},
    {"date": "2026-06-25", "home": "Japan", "away": "Sweden", "group": "F", "stadium": "Dallas Stadium", "region": "Texas"},
    {"date": "2026-06-25", "home": "Tunisia", "away": "Netherlands", "group": "F", "stadium": "Kansas City Stadium", "region": "Missouri"},
    {"date": "2026-06-25", "home": "Turkiye", "away": "USA", "group": "D", "stadium": "Los Angeles Stadium", "region": "California"},
    {"date": "2026-06-25", "home": "Paraguay", "away": "Australia", "group": "D", "stadium": "San Francisco Bay Area Stadium", "region": "California"},
    {"date": "2026-06-26", "home": "Norway", "away": "France", "group": "I", "stadium": "Boston Stadium", "region": "Massachusetts"},
    {"date": "2026-06-26", "home": "Senegal", "away": "Iraq", "group": "I", "stadium": "Toronto Stadium", "region": "Ontario"},
    {"date": "2026-06-26", "home": "Egypt", "away": "IR Iran", "group": "G", "stadium": "Seattle Stadium", "region": "Washington"},
    {"date": "2026-06-26", "home": "New Zealand", "away": "Belgium", "group": "G", "stadium": "BC Place Vancouver", "region": "British Columbia"},
    {"date": "2026-06-26", "home": "Cabo Verde", "away": "Saudi Arabia", "group": "H", "stadium": "Houston Stadium", "region": "Texas"},
    {"date": "2026-06-26", "home": "Uruguay", "away": "Spain", "group": "H", "stadium": "Estadio Guadalajara", "region": "Jalisco"},
    {"date": "2026-06-27", "home": "Panama", "away": "England", "group": "L", "stadium": "New York/New Jersey Stadium", "region": "New Jersey"},
    {"date": "2026-06-27", "home": "Croatia", "away": "Ghana", "group": "L", "stadium": "Philadelphia Stadium", "region": "Pennsylvania"},
    {"date": "2026-06-27", "home": "Algeria", "away": "Austria", "group": "J", "stadium": "Kansas City Stadium", "region": "Missouri"},
    {"date": "2026-06-27", "home": "Jordan", "away": "Argentina", "group": "J", "stadium": "Dallas Stadium", "region": "Texas"},
    {"date": "2026-06-27", "home": "Colombia", "away": "Portugal", "group": "K", "stadium": "Miami Stadium", "region": "Florida"},
    {"date": "2026-06-27", "home": "Congo DR", "away": "Uzbekistan", "group": "K", "stadium": "Atlanta Stadium", "region": "Georgia"},
]

WORLD_CUP_FLAG_URLS = {
    "Algeria": "https://a.espncdn.com/i/teamlogos/countries/500/alg.png",
    "Argentina": "https://a.espncdn.com/i/teamlogos/countries/500/arg.png",
    "Australia": "https://a.espncdn.com/i/teamlogos/countries/500/aus.png",
    "Austria": "https://a.espncdn.com/i/teamlogos/countries/500/aut.png",
    "Belgium": "https://a.espncdn.com/i/teamlogos/countries/500/bel.png",
    "Bosnia and Herzegovina": "https://a.espncdn.com/i/teamlogos/countries/500/bih.png",
    "Brazil": "https://a.espncdn.com/i/teamlogos/countries/500/bra.png",
    "Cabo Verde": "https://a.espncdn.com/i/teamlogos/countries/500/cpv.png",
    "Canada": "https://a.espncdn.com/i/teamlogos/countries/500/can.png",
    "Colombia": "https://a.espncdn.com/i/teamlogos/countries/500/col.png",
    "Congo DR": "https://a.espncdn.com/i/teamlogos/countries/500/rdc.png",
    "Cote d'Ivoire": "https://a.espncdn.com/i/teamlogos/countries/500/civ.png",
    "Croatia": "https://a.espncdn.com/i/teamlogos/countries/500/cro.png",
    "Curacao": "https://a.espncdn.com/i/teamlogos/soccer/500/11678.png",
    "Czechia": "https://a.espncdn.com/i/teamlogos/countries/500/cze.png",
    "Ecuador": "https://a.espncdn.com/i/teamlogos/countries/500/ecu.png",
    "Egypt": "https://a.espncdn.com/i/teamlogos/countries/500/egy.png",
    "England": "https://a.espncdn.com/i/teamlogos/countries/500/eng.png",
    "France": "https://a.espncdn.com/i/teamlogos/countries/500/fra.png",
    "Germany": "https://a.espncdn.com/i/teamlogos/countries/500/ger.png",
    "Ghana": "https://a.espncdn.com/i/teamlogos/countries/500/gha.png",
    "Haiti": "https://a.espncdn.com/i/teamlogos/countries/500/hai.png",
    "IR Iran": "https://a.espncdn.com/i/teamlogos/countries/500/irn.png",
    "Iraq": "https://a.espncdn.com/i/teamlogos/countries/500/irq.png",
    "Japan": "https://a.espncdn.com/i/teamlogos/countries/500/jpn.png",
    "Jordan": "https://a.espncdn.com/i/teamlogos/countries/500/jor.png",
    "Korea Republic": "https://a.espncdn.com/i/teamlogos/countries/500/kor.png",
    "Mexico": "https://a.espncdn.com/i/teamlogos/countries/500/mex.png",
    "Morocco": "https://a.espncdn.com/i/teamlogos/countries/500/mar.png",
    "Netherlands": "https://a.espncdn.com/i/teamlogos/countries/500/ned.png",
    "New Zealand": "https://a.espncdn.com/i/teamlogos/countries/500/nzl.png",
    "Norway": "https://a.espncdn.com/i/teamlogos/countries/500/nor.png",
    "Panama": "https://a.espncdn.com/i/teamlogos/countries/500/pan.png",
    "Paraguay": "https://a.espncdn.com/i/teamlogos/countries/500/par.png",
    "Portugal": "https://a.espncdn.com/i/teamlogos/countries/500/por.png",
    "Qatar": "https://a.espncdn.com/i/teamlogos/countries/500/qat.png",
    "Saudi Arabia": "https://a.espncdn.com/i/teamlogos/countries/500/ksa.png",
    "Scotland": "https://a.espncdn.com/i/teamlogos/countries/500/sco.png",
    "Senegal": "https://a.espncdn.com/i/teamlogos/countries/500/sen.png",
    "South Africa": "https://a.espncdn.com/i/teamlogos/countries/500/rsa.png",
    "Spain": "https://a.espncdn.com/i/teamlogos/countries/500/esp.png",
    "Sweden": "https://a.espncdn.com/i/teamlogos/countries/500/swe.png",
    "Switzerland": "https://a.espncdn.com/i/teamlogos/countries/500/sui.png",
    "Tunisia": "https://a.espncdn.com/i/teamlogos/countries/500/tun.png",
    "Turkiye": "https://a.espncdn.com/i/teamlogos/countries/500/tur.png",
    "USA": "https://a.espncdn.com/i/teamlogos/countries/500/usa.png",
    "Uruguay": "https://a.espncdn.com/i/teamlogos/countries/500/uru.png",
    "Uzbekistan": "https://a.espncdn.com/i/teamlogos/countries/500/uzb.png",
}

WORLD_CUP_STATIC_TOP_SCORERS = [
    {"rank": 1, "player": "Lionel Messi", "team": "Argentina", "goals": 3, "matches": 1, "team_flag": WORLD_CUP_FLAG_URLS["Argentina"]},
    {"rank": 2, "player": "Yasin Ayari", "team": "Sweden", "goals": 2, "matches": 1, "team_flag": WORLD_CUP_FLAG_URLS["Sweden"]},
    {"rank": 3, "player": "Elijah Just", "team": "New Zealand", "goals": 2, "matches": 1, "team_flag": WORLD_CUP_FLAG_URLS["New Zealand"]},
    {"rank": 4, "player": "Erling Haaland", "team": "Norway", "goals": 2, "matches": 1, "team_flag": WORLD_CUP_FLAG_URLS["Norway"]},
    {"rank": 5, "player": "Kylian Mbappe", "team": "France", "goals": 2, "matches": 1, "team_flag": WORLD_CUP_FLAG_URLS["France"]},
]

NEWS_RELEVANCE_KEYWORDS = {
    "macro": [
        "banco central",
        "central bank",
        "copom",
        "selic",
        "fed",
        "federal reserve",
        "juros",
        "rate",
        "rates",
        "inflacao",
        "inflação",
        "ipca",
        "cpi",
        "pce",
        "recessao",
        "recessão",
        "gdp",
        "pib",
        "treasury",
        "yield",
        "fiscal",
        "deficit",
        "déficit",
        "tarifa",
        "tariff",
    ],
    "markets": [
        "mercado",
        "markets",
        "market",
        "bolsa",
        "stocks",
        "stock",
        "shares",
        "ações",
        "acoes",
        "ibovespa",
        "s&p",
        "nasdaq",
        "dow",
        "dax",
        "nikkei",
        "dolar",
        "dólar",
        "currency",
        "oil",
        "petroleo",
        "petróleo",
        "commodities",
        "bitcoin",
        "crypto",
        "earnings",
        "ipo",
    ],
    "business": [
        "empresa",
        "company",
        "ceo",
        "lucro",
        "profit",
        "receita",
        "revenue",
        "m&a",
        "merger",
        "acquisition",
        "deal",
        "valuation",
        "debt",
        "dívida",
        "divida",
        "bank",
        "banco",
        "tech",
        "technology",
        "ai",
        "ia",
        "nvidia",
        "apple",
        "amazon",
        "google",
        "microsoft",
        "tesla",
        "spacex",
    ],
    "geopolitics": [
        "eua",
        "usa",
        "u.s.",
        "us ",
        "china",
        "brasil",
        "brazil",
        "lula",
        "trump",
        "congresso",
        "supremo",
        "stf",
        "war",
        "guerra",
        "iran",
        "irã",
        "israel",
        "ukraine",
        "ucrânia",
        "russia",
        "rússia",
        "gaza",
        "sanction",
        "sanções",
        "sancoes",
        "election",
        "eleição",
        "eleicao",
    ],
}

GLOBO_ALLOWED_NEWS_TERMS = (
    "economia",
    "mercado",
    "mercados",
    "politica",
    "política",
    "congresso",
    "camara",
    "câmara",
    "senado",
    "stf",
    "supremo",
    "governo",
    "fazenda",
    "banco central",
    "copom",
    "selic",
    "juros",
    "inflacao",
    "inflação",
    "ipca",
    "dolar",
    "dólar",
    "ibovespa",
    "bolsa",
    "acoes",
    "ações",
    "pib",
    "fiscal",
    "tarifa",
)

NEWS_NOISE_KEYWORDS = [
    "copa do mundo",
    "futebol",
    "neymar",
    "seleção",
    "selecao",
    "placar",
    "jogo",
    "gol",
    "bbb",
    "novela",
    "celebridade",
    "gravidez",
    "horoscopo",
    "horóscopo",
    "receita de",
    "promoção",
    "promocao",
    "desconto",
    "oferta",
    "aprovados",
    "concurso",
    "bairro",
]


def report_title_for_time(now=None):
    now = now or dt.datetime.now(TIMEZONE)
    if now.hour < 12:
        return "Morning Summary"
    if now.hour < 19:
        return "Lunch Summary"
    return "Night Summary"


def report_slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

CHEAP_STOCKS = {
    "B3": [
        {
            "ticker": "COGN3",
            "multiples": "P/E N/D | Forward P/E N/D | PEG N/D | EV/EBITDA N/D",
            "thesis": "Turnaround com upside alto; captação, ticket e desalavancagem são gatilhos de rerating.",
            "risk": "Execução, alavancagem e evasão podem consumir o upside.",
        },
        {
            "ticker": "MRVE3",
            "multiples": "P/E N/D | Forward P/E N/D | PEG N/D | EV/EBITDA N/D",
            "thesis": "Valuation deprimido + queda de juros/MCMV podem acelerar vendas, margem e caixa.",
            "risk": "Endividamento, distratos e execução mantêm a tese cíclica.",
        },
        {
            "ticker": "YDUQ3",
            "multiples": "P/E N/D | Forward P/E N/D | PEG N/D | EV/EBITDA N/D",
            "thesis": "Recuperação operacional; base de alunos, inadimplência e dívida são os gatilhos.",
            "risk": "Regulação, competição e inadimplência podem atrasar a virada.",
        },
        {
            "ticker": "CYRE3",
            "multiples": "P/E N/D | Forward P/E N/D | PEG N/D | EV/EBITDA N/D",
            "thesis": "Forma mais limpa de capturar queda de juros: marca forte, execução e desconto patrimonial.",
            "risk": "Vendas, custos de obra e ciclo imobiliário são os riscos-chave.",
        },
        {
            "ticker": "TOTS3",
            "multiples": "P/E N/D | Forward P/E N/D | PEG N/D | EV/EBITDA N/D",
            "thesis": "Qualidade defensiva: receita recorrente, alto ROIC e upside se margem/crescimento acelerarem.",
            "risk": "Não é deep value; desaceleração em software reduz o prêmio.",
        },
    ],
    "Nasdaq": [
        {
            "ticker": "CHTR",
            "multiples": "P/E 3,94 | Forward P/E 3,28 | PEG 0,25",
            "thesis": "Maior combinação de upside e múltiplos baixos no screening Nasdaq; desalavancagem e FCF podem destravar rerating.",
            "risk": "Dívida elevada, pressão competitiva em broadband e queda de assinantes de TV.",
        },
        {
            "ticker": "PDD",
            "multiples": "P/E 8,72 | Forward P/E 7,34 | PEG 0,99",
            "thesis": "Upside alto com crescimento ainda robusto; Temu e China commerce podem justificar múltiplo maior se margens sustentarem.",
            "risk": "Regulação, geopolítica, margens de Temu e competição.",
        },
        {
            "ticker": "TCOM",
            "multiples": "P/E 6,82 | Forward P/E 11,25",
            "thesis": "Upside muito alto com múltiplos ainda razoáveis; turismo chinês e internacional podem sustentar crescimento.",
            "risk": "Consumo chinês, competição em viagens online e risco macro/ADR.",
        },
        {
            "ticker": "ADBE",
            "multiples": "P/E 11,67 | Forward P/E 7,89 | PEG 0,58",
            "thesis": "Screening aponta múltiplos comprimidos versus qualidade; AI e Creative Cloud podem sustentar rerating se crescimento voltar.",
            "risk": "Competição em AI criativa, pressão de preços e execução em monetização.",
        },
        {
            "ticker": "JD",
            "multiples": "P/E 21,60 | Forward P/E 8,01 | PEG 0,30",
            "thesis": "Consenso aponta upside expressivo; logística própria e disciplina de capital podem sustentar recuperação se consumo chinês melhorar.",
            "risk": "Consumo fraco na China, margens apertadas e competição.",
        },
    ],
    "NYSE": [
        {
            "ticker": "TME",
            "multiples": "P/E 11,18 | Forward P/E 9,30 | PEG 0,79",
            "thesis": "Maior score NYSE no screening; música/entretenimento na China com crescimento e múltiplos ainda baixos.",
            "risk": "China, ADR, regulação de conteúdo e concorrência em streaming.",
        },
        {
            "ticker": "CRM",
            "multiples": "P/E 19,26 | Forward P/E 11,92 | PEG 0,74",
            "thesis": "Software corporativo de alta qualidade; margem, IA e disciplina de capital podem sustentar rerating.",
            "risk": "Crescimento menor, competição em CRM/IA e execução de aquisições.",
        },
        {
            "ticker": "TAL",
            "multiples": "P/E 10,10 | Forward P/E 10,84 | PEG 0,50",
            "thesis": "Alto upside e valuation razoável para educação chinesa pós-reestruturação; pode reratear se crescimento continuar.",
            "risk": "Regulação educacional na China, ADR e volatilidade de margens.",
        },
        {
            "ticker": "CHWY",
            "multiples": "P/E 32,25 | Forward P/E 12,09 | PEG 0,38",
            "thesis": "Consumo pet com base recorrente; margem operacional e recompras podem destravar valor.",
            "risk": "Crescimento mais lento, competição e sensibilidade do consumidor.",
        },
        {
            "ticker": "BABA",
            "multiples": "P/E 17,68 | Forward P/E 16,79 | PEG 0,50",
            "thesis": "Grande upside de consenso com valuation ainda descontado; cloud, e-commerce e recompras podem destravar valor.",
            "risk": "China, ADR, competição e incerteza regulatória.",
        },
    ],
}

CANDIDATE_UNIVERSE = {
    "B3": [
        {"ticker": "COGN3", "symbol": "COGN3.SA", "sector": "Educação", "quality": 38, "ai": 52, "turnaround": True, "catalyst": "margem, caixa e recuperação de alunos", "risk": "turnaround, alavancagem e execução"},
        {"ticker": "MRVE3", "symbol": "MRVE3.SA", "sector": "Construção", "quality": 42, "ai": 54, "turnaround": True, "catalyst": "queda de juros, MCMV e liberação de caixa", "risk": "dívida, distratos e ciclo imobiliário"},
        {"ticker": "YDUQ3", "symbol": "YDUQ3.SA", "sector": "Educação", "quality": 48, "ai": 57, "turnaround": True, "catalyst": "inadimplência menor e desalavancagem", "risk": "regulação, competição e execução"},
        {"ticker": "CYRE3", "symbol": "CYRE3.SA", "sector": "Construção", "quality": 72, "ai": 70, "catalyst": "queda de juros e velocidade de vendas", "risk": "custo de obra e ciclo imobiliário"},
        {"ticker": "TOTS3", "symbol": "TOTS3.SA", "sector": "Software", "quality": 86, "ai": 76, "catalyst": "receita recorrente, margem e cross-sell", "risk": "valuation ainda exige crescimento"},
        {"ticker": "PETR4", "symbol": "PETR4.SA", "sector": "Energia", "quality": 62, "ai": 55, "catalyst": "dividendos e disciplina de capex", "risk": "governança estatal e petróleo"},
        {"ticker": "VALE3", "symbol": "VALE3.SA", "sector": "Mineração", "quality": 70, "ai": 58, "catalyst": "minério, dividendos e China", "risk": "commodities e passivos ambientais"},
        {"ticker": "BBAS3", "symbol": "BBAS3.SA", "sector": "Bancos", "quality": 76, "ai": 64, "catalyst": "ROE alto e dividendos", "risk": "crédito e interferência estatal"},
        {"ticker": "ITUB4", "symbol": "ITUB4.SA", "sector": "Bancos", "quality": 88, "ai": 72, "catalyst": "qualidade de crédito e ROE", "risk": "valuation menos descontado"},
        {"ticker": "BBDC4", "symbol": "BBDC4.SA", "sector": "Bancos", "quality": 66, "ai": 62, "turnaround": True, "catalyst": "normalização de ROE e provisões", "risk": "qualidade de crédito"},
        {"ticker": "WEGE3", "symbol": "WEGE3.SA", "sector": "Industriais", "quality": 92, "ai": 76, "catalyst": "crescimento global e eficiência", "risk": "valuation premium"},
        {"ticker": "PRIO3", "symbol": "PRIO3.SA", "sector": "Energia", "quality": 78, "ai": 70, "catalyst": "produção, M&A e eficiência operacional", "risk": "execução e petróleo"},
        {"ticker": "RAIL3", "symbol": "RAIL3.SA", "sector": "Logística", "quality": 68, "ai": 62, "catalyst": "volume agrícola e eficiência", "risk": "capex e regulação"},
        {"ticker": "LREN3", "symbol": "LREN3.SA", "sector": "Varejo", "quality": 74, "ai": 64, "catalyst": "ciclo de consumo e margem", "risk": "competição e crédito"},
    ],
    "Nasdaq": [
        {"ticker": "CHTR", "symbol": "CHTR", "sector": "Comunicações", "quality": 58, "ai": 62, "catalyst": "FCF e desalavancagem", "risk": "dívida e competição em broadband"},
        {"ticker": "PDD", "symbol": "PDD", "sector": "E-commerce", "quality": 76, "ai": 68, "china": True, "catalyst": "crescimento de Temu e China commerce", "risk": "China, geopolítica e margens"},
        {"ticker": "TCOM", "symbol": "TCOM", "sector": "Viagens", "quality": 72, "ai": 66, "china": True, "catalyst": "recuperação de viagens na China", "risk": "consumo chinês e ADR"},
        {"ticker": "ADBE", "symbol": "ADBE", "sector": "Software", "quality": 90, "ai": 74, "catalyst": "monetização de IA e Creative Cloud", "risk": "concorrência em IA criativa"},
        {"ticker": "JD", "symbol": "JD", "sector": "E-commerce", "quality": 64, "ai": 58, "china": True, "catalyst": "recompras e logística", "risk": "consumo China e margens"},
        {"ticker": "PYPL", "symbol": "PYPL", "sector": "Fintech", "quality": 70, "ai": 64, "turnaround": True, "catalyst": "margem, checkout e recompras", "risk": "competição e crescimento baixo"},
        {"ticker": "GOOGL", "symbol": "GOOGL", "sector": "Internet", "quality": 92, "ai": 78, "catalyst": "AI, cloud e publicidade", "risk": "antitruste e capex de IA"},
        {"ticker": "META", "symbol": "META", "sector": "Internet", "quality": 90, "ai": 76, "catalyst": "ads, IA e eficiência", "risk": "capex e regulação"},
        {"ticker": "QCOM", "symbol": "QCOM", "sector": "Semicondutores", "quality": 78, "ai": 68, "catalyst": "AI edge, handsets e autos", "risk": "ciclo de chips e Apple"},
        {"ticker": "MU", "symbol": "MU", "sector": "Semicondutores", "quality": 64, "ai": 64, "cyclical": True, "catalyst": "memória/AI e pricing", "risk": "ciclo agressivo de memória"},
        {"ticker": "INTC", "symbol": "INTC", "sector": "Semicondutores", "quality": 42, "ai": 46, "turnaround": True, "catalyst": "foundry e cortes de custo", "risk": "execução e capex alto"},
        {"ticker": "GILD", "symbol": "GILD", "sector": "Saúde", "quality": 72, "ai": 60, "catalyst": "pipeline e dividendos", "risk": "expiração de patentes"},
        {"ticker": "CSCO", "symbol": "CSCO", "sector": "Tecnologia", "quality": 74, "ai": 58, "catalyst": "software e dividendos", "risk": "crescimento baixo"},
        {"ticker": "IBIT", "symbol": "IBIT", "sector": "ETF Cripto", "quality": 66, "ai": 66, "etf": True, "etf_value": 62, "catalyst": "recuperação do bitcoin, fluxo institucional e liquidez do ETF", "risk": "volatilidade extrema de cripto e correlação com apetite a risco", "multiples": "P/E 0.00 | FWRD P/E 0.00 | EV/EBITDA 0.00 | PEG Ratio 0.00"},
        {"ticker": "QQQ", "symbol": "QQQ", "sector": "ETF Tecnologia", "quality": 88, "ai": 72, "etf": True, "etf_value": 74, "catalyst": "megacaps de tecnologia, IA e lucros do Nasdaq 100", "risk": "concentração em tecnologia e valuation de megacaps", "multiples": "P/E 30.00 | FWRD P/E 25.00 | EV/EBITDA 0.00 | PEG Ratio 1.50"},
        {"ticker": "SMH", "symbol": "SMH", "sector": "ETF Semicondutores", "quality": 82, "ai": 74, "etf": True, "etf_value": 72, "catalyst": "semicondutores ligados a IA e capex de data centers", "risk": "ciclo de chips, concentração e valuation elevado", "multiples": "P/E 34.00 | FWRD P/E 27.00 | EV/EBITDA 0.00 | PEG Ratio 1.60"},
        {"ticker": "SOXX", "symbol": "SOXX", "sector": "ETF Semicondutores", "quality": 80, "ai": 72, "etf": True, "etf_value": 70, "catalyst": "cadeia de semicondutores e demanda de IA", "risk": "ciclo de chips e concentração setorial", "multiples": "P/E 32.00 | FWRD P/E 26.00 | EV/EBITDA 0.00 | PEG Ratio 1.55"},
        {"ticker": "CIBR", "symbol": "CIBR", "sector": "ETF Cybersecurity", "quality": 76, "ai": 66, "etf": True, "etf_value": 66, "catalyst": "segurança cibernética, gasto corporativo e recorrência de software", "risk": "valuation de software e competição entre fornecedores", "multiples": "P/E 28.00 | FWRD P/E 24.00 | EV/EBITDA 0.00 | PEG Ratio 1.40"},
        {"ticker": "ICLN", "symbol": "ICLN", "sector": "ETF Energia Limpa", "quality": 48, "ai": 50, "etf": True, "etf_value": 48, "turnaround": True, "catalyst": "queda de juros e recuperação de energia limpa", "risk": "juros, subsídios, margens fracas e competição", "multiples": "P/E 19.00 | FWRD P/E 17.00 | EV/EBITDA 0.00 | PEG Ratio 1.20"},
    ],
    "NYSE": [
        {"ticker": "TME", "symbol": "TME", "sector": "Mídia", "quality": 72, "ai": 64, "china": True, "catalyst": "assinantes pagantes e ARPU", "risk": "China, ADR e conteúdo"},
        {"ticker": "TAL", "symbol": "TAL", "sector": "Educação", "quality": 56, "ai": 55, "china": True, "turnaround": True, "catalyst": "crescimento pós-regulação", "risk": "risco regulatório chinês"},
        {"ticker": "FUTU", "symbol": "FUTU", "sector": "Fintech", "quality": 70, "ai": 58, "china": True, "catalyst": "mercado China/HK mais forte", "risk": "regulação e volatilidade"},
        {"ticker": "BABA", "symbol": "BABA", "sector": "E-commerce", "quality": 76, "ai": 66, "china": True, "catalyst": "cloud, recompras e e-commerce", "risk": "China, competição e ADR"},
        {"ticker": "CRM", "symbol": "CRM", "sector": "Software", "quality": 86, "ai": 68, "catalyst": "margem, IA corporativa e disciplina de capital", "risk": "crescimento menor, competição em CRM/IA e execução"},
        {"ticker": "CHWY", "symbol": "CHWY", "sector": "Consumo", "quality": 54, "ai": 50, "catalyst": "margem operacional, base recorrente e recompras", "risk": "crescimento mais lento, competição e consumidor apertado"},
        {"ticker": "BILL", "symbol": "BILL", "sector": "Software", "quality": 54, "ai": 56, "turnaround": True, "catalyst": "retomada de crescimento e margem", "risk": "SMB fintech e competição"},
        {"ticker": "RBLX", "symbol": "RBLX", "sector": "Mídia", "quality": 42, "ai": 60, "catalyst": "monetização, crescimento de usuários e disciplina de custos", "risk": "rentabilidade, valuation e dependência de engajamento"},
        {"ticker": "FMC", "symbol": "FMC", "sector": "Materiais", "quality": 52, "ai": 48, "turnaround": True, "catalyst": "fim do destocking agroquímico e normalização de demanda", "risk": "agro fraco, alavancagem e pressão de preços"},
        {"ticker": "DIS", "symbol": "DIS", "sector": "Mídia", "quality": 68, "ai": 62, "turnaround": True, "catalyst": "streaming lucrativo e parques", "risk": "mídia linear e execução"},
        {"ticker": "NKE", "symbol": "NKE", "sector": "Consumo", "quality": 76, "ai": 58, "turnaround": True, "catalyst": "reposicionamento de produto", "risk": "concorrência e China"},
        {"ticker": "BMY", "symbol": "BMY", "sector": "Saúde", "quality": 66, "ai": 60, "catalyst": "pipeline e dividendos", "risk": "patentes e execução clínica"},
        {"ticker": "PFE", "symbol": "PFE", "sector": "Saúde", "quality": 58, "ai": 54, "turnaround": True, "catalyst": "pipeline e cortes de custo", "risk": "queda pós-Covid e dívida"},
        {"ticker": "CVS", "symbol": "CVS", "sector": "Saúde", "quality": 54, "ai": 50, "turnaround": True, "catalyst": "normalização de custos médicos", "risk": "pressão em seguros"},
        {"ticker": "VZ", "symbol": "VZ", "sector": "Telecom", "quality": 62, "ai": 54, "catalyst": "dividendos e FCF", "risk": "dívida e baixo crescimento"},
        {"ticker": "C", "symbol": "C", "sector": "Bancos", "quality": 56, "ai": 58, "turnaround": True, "catalyst": "reestruturação e capital", "risk": "execução e ciclo de crédito"},
        {"ticker": "OXY", "symbol": "OXY", "sector": "Energia", "quality": 68, "ai": 58, "catalyst": "petróleo e desalavancagem", "risk": "commodity e dívida"},
        {"ticker": "KWEB", "symbol": "KWEB", "sector": "ETF China Internet", "quality": 64, "ai": 62, "china": True, "etf": True, "etf_value": 58, "catalyst": "internet chinesa, estímulo doméstico e rerating de ADRs/H shares", "risk": "China, regulação, geopolítica e volatilidade de fluxo", "multiples": "P/E 13.00 | FWRD P/E 11.00 | EV/EBITDA 0.00 | PEG Ratio 1.00"},
        {"ticker": "ARKF", "symbol": "ARKF", "sector": "ETF Fintech", "quality": 46, "ai": 58, "etf": True, "etf_value": 48, "turnaround": True, "catalyst": "fintech, blockchain, pagamentos digitais e retomada de growth", "risk": "valuation de growth, juros e alta concentração temática", "multiples": "P/E 0.00 | FWRD P/E 0.00 | EV/EBITDA 0.00 | PEG Ratio 0.00"},
        {"ticker": "FINX", "symbol": "FINX", "sector": "ETF Fintech", "quality": 56, "ai": 58, "etf": True, "etf_value": 54, "catalyst": "pagamentos, software financeiro e digitalização bancária", "risk": "juros, competição e revisão de crescimento em fintech", "multiples": "P/E 22.00 | FWRD P/E 19.00 | EV/EBITDA 0.00 | PEG Ratio 1.25"},
        {"ticker": "BKCH", "symbol": "BKCH", "sector": "ETF Blockchain", "quality": 42, "ai": 54, "etf": True, "etf_value": 46, "cyclical": True, "catalyst": "ações ligadas a blockchain e ciclo de cripto", "risk": "volatilidade extrema, cripto e concentração temática", "multiples": "P/E 0.00 | FWRD P/E 0.00 | EV/EBITDA 0.00 | PEG Ratio 0.00"},
        {"ticker": "GDX", "symbol": "GDX", "sector": "ETF Gold Miners", "quality": 58, "ai": 50, "etf": True, "etf_value": 54, "cyclical": True, "catalyst": "ouro, margens de mineradoras e dólar/juros reais", "risk": "preço do ouro, custos de mineração e ciclo de commodities", "multiples": "P/E 18.00 | FWRD P/E 15.00 | EV/EBITDA 0.00 | PEG Ratio 1.10"},
        {"ticker": "GDXJ", "symbol": "GDXJ", "sector": "ETF Junior Gold Miners", "quality": 48, "ai": 48, "etf": True, "etf_value": 48, "cyclical": True, "catalyst": "ouro e maior beta em mineradoras junior", "risk": "commodity, empresas menores e volatilidade elevada", "multiples": "P/E 19.00 | FWRD P/E 16.00 | EV/EBITDA 0.00 | PEG Ratio 1.20"},
        {"ticker": "SLV", "symbol": "SLV", "sector": "ETF Silver", "quality": 54, "ai": 50, "etf": True, "etf_value": 50, "cyclical": True, "catalyst": "prata, demanda industrial e metais preciosos", "risk": "commodity sem fluxo de caixa e volatilidade elevada", "multiples": "P/E 0.00 | FWRD P/E 0.00 | EV/EBITDA 0.00 | PEG Ratio 0.00"},
        {"ticker": "ARKK", "symbol": "ARKK", "sector": "ETF Innovation", "quality": 42, "ai": 58, "etf": True, "etf_value": 44, "turnaround": True, "catalyst": "growth disruptivo, IA e queda de juros", "risk": "alta volatilidade, valuation e concentração em growth sem lucro", "multiples": "P/E 0.00 | FWRD P/E 0.00 | EV/EBITDA 0.00 | PEG Ratio 0.00"},
    ],
}

CANDIDATE_BASE_CACHE = {}
YAHOO_QUOTE_CACHE = {}
YAHOO_CHART_META_CACHE = {}
CANDIDATE_IS_ETF = {}
CANDIDATE_NAMES = {}
FINVIZ_PEG_CACHE = {}
STOCKANALYSIS_GROWTH_CACHE = {}
MIN_CANDIDATE_UPSIDE_PCT = 40.0
MIN_CANDIDATE_BUY_IN_DISTANCE_PCT = -100.0
MAX_CANDIDATE_BUY_IN_DISTANCE_PCT = 15.0
MIN_WATCHLIST_BUY_IN_DISTANCE_PCT = -100.0
MAX_WATCHLIST_BUY_IN_DISTANCE_PCT = 30.0
BROAD_CANDIDATE_SCREENING = os.getenv("CANDIDATE_BROAD_SCREENING", "1").lower() not in {"0", "false", "no"}
BROAD_B3_PREFILTER_LIMIT = int(os.getenv("CANDIDATE_B3_PREFILTER_LIMIT", "200"))
BROAD_NASDAQ_PREFILTER_LIMIT = int(os.getenv("CANDIDATE_NASDAQ_PREFILTER_LIMIT", "300"))
BROAD_NYSE_PREFILTER_LIMIT = int(os.getenv("CANDIDATE_NYSE_PREFILTER_LIMIT", "300"))
BROAD_US_ETF_PREFILTER_LIMIT = int(os.getenv("CANDIDATE_US_ETF_PREFILTER_LIMIT", "50"))
CANDIDATE_FINAL_REVIEW_LIMITS = {
    "B3": int(os.getenv("CANDIDATE_B3_FINAL_REVIEW_LIMIT", "200")),
    "Nasdaq": int(os.getenv("CANDIDATE_NASDAQ_FINAL_REVIEW_LIMIT", "300")),
    "NYSE": int(os.getenv("CANDIDATE_NYSE_FINAL_REVIEW_LIMIT", "300")),
}
CANDIDATE_DISPLAY_LIMITS = {
    "B3": int(os.getenv("CANDIDATE_B3_DISPLAY_LIMIT", "10")),
    "Nasdaq": int(os.getenv("CANDIDATE_NASDAQ_DISPLAY_LIMIT", "5")),
    "NYSE": int(os.getenv("CANDIDATE_NYSE_DISPLAY_LIMIT", "5")),
}
CANDIDATE_SNAPSHOT_WORKERS = int(os.getenv("CANDIDATE_SNAPSHOT_WORKERS", "12"))

B3_BROAD_TICKERS = [
    ("ABEV3", "Consumo", 78, 58),
    ("ALUP11", "Utilidades", 72, 58),
    ("ASAI3", "Varejo", 62, 56),
    ("AURE3", "Utilidades", 66, 54),
    ("AZUL4", "Transporte", 36, 48),
    ("B3SA3", "Financeiro", 82, 64),
    ("BBAS3", "Bancos", 76, 64),
    ("BBDC3", "Bancos", 64, 60),
    ("BBDC4", "Bancos", 66, 62),
    ("BBSE3", "Seguros", 80, 60),
    ("BEEF3", "Alimentos", 46, 48),
    ("BPAC11", "Bancos", 82, 66),
    ("BRAP4", "Mineração", 64, 56),
    ("BRAV3", "Energia", 58, 54),
    ("BRFS3", "Alimentos", 56, 56),
    ("CCRO3", "Infraestrutura", 66, 56),
    ("CMIG4", "Utilidades", 72, 58),
    ("CMIN3", "Mineração", 64, 54),
    ("COGN3", "Educação", 38, 52),
    ("CPFE3", "Utilidades", 76, 58),
    ("CPLE6", "Utilidades", 74, 58),
    ("CRFB3", "Varejo", 44, 48),
    ("CSAN3", "Energia", 62, 58),
    ("CSNA3", "Siderurgia", 52, 54),
    ("CURY3", "Construção", 68, 58),
    ("CYRE3", "Construção", 72, 70),
    ("DIRR3", "Construção", 66, 58),
    ("DXCO3", "Construção", 52, 50),
    ("EGIE3", "Utilidades", 82, 60),
    ("ELET3", "Utilidades", 76, 62),
    ("ELET6", "Utilidades", 74, 60),
    ("EMBR3", "Industriais", 76, 66),
    ("ENEV3", "Utilidades", 58, 54),
    ("EQTL3", "Utilidades", 84, 64),
    ("EZTC3", "Construção", 58, 52),
    ("FLRY3", "Saúde", 70, 56),
    ("GGBR4", "Siderurgia", 66, 58),
    ("GMAT3", "Varejo", 62, 54),
    ("GOAU4", "Siderurgia", 62, 54),
    ("HAPV3", "Saúde", 44, 52),
    ("HYPE3", "Saúde", 72, 58),
    ("IGTI11", "Imobiliário", 66, 56),
    ("ITSA4", "Bancos", 82, 62),
    ("ITUB4", "Bancos", 88, 72),
    ("JBSS3", "Alimentos", 68, 58),
    ("KLBN11", "Papel e Celulose", 72, 58),
    ("LREN3", "Varejo", 74, 64),
    ("LWSA3", "Tecnologia", 42, 50),
    ("MGLU3", "Varejo", 34, 48),
    ("MRFG3", "Alimentos", 42, 48),
    ("MRVE3", "Construção", 42, 54),
    ("MULT3", "Imobiliário", 74, 60),
    ("NTCO3", "Consumo", 42, 50),
    ("ONCO3", "Saúde", 48, 52),
    ("PCAR3", "Varejo", 32, 42),
    ("PETR3", "Energia", 64, 56),
    ("PETR4", "Energia", 62, 55),
    ("PETZ3", "Varejo", 42, 48),
    ("POMO4", "Industriais", 62, 54),
    ("PRIO3", "Energia", 78, 70),
    ("PSSA3", "Seguros", 78, 58),
    ("RADL3", "Varejo", 84, 64),
    ("RAIL3", "Logística", 68, 62),
    ("RAIZ4", "Energia", 42, 50),
    ("RDOR3", "Saúde", 66, 56),
    ("RECV3", "Energia", 52, 54),
    ("RENT3", "Locação", 76, 64),
    ("SANB11", "Bancos", 72, 58),
    ("SBSP3", "Utilidades", 82, 66),
    ("SLCE3", "Agro", 68, 58),
    ("SMTO3", "Agro", 62, 54),
    ("SUZB3", "Papel e Celulose", 74, 60),
    ("TAEE11", "Utilidades", 78, 58),
    ("TIMS3", "Telecom", 74, 56),
    ("TOTS3", "Software", 86, 76),
    ("UGPA3", "Energia", 66, 56),
    ("USIM5", "Siderurgia", 46, 48),
    ("VALE3", "Mineração", 70, 58),
    ("VBBR3", "Energia", 64, 56),
    ("VIVA3", "Varejo", 60, 54),
    ("VIVT3", "Telecom", 80, 58),
    ("WEGE3", "Industriais", 92, 76),
    ("YDUQ3", "Educação", 48, 57),
]

B3_TURNAROUND_TICKERS = {
    "AZUL4", "BBDC4", "BEEF3", "BRFS3", "COGN3", "CRFB3", "HAPV3",
    "LWSA3", "MGLU3", "MRFG3", "MRVE3", "NTCO3", "ONCO3", "PCAR3",
    "PETZ3", "RAIZ4", "YDUQ3",
}
B3_CYCLICAL_TICKERS = {
    "AZUL4", "BRAP4", "BRAV3", "CMIN3", "CSNA3", "CURY3", "CYRE3",
    "DIRR3", "DXCO3", "EZTC3", "GGBR4", "GOAU4", "JBSS3", "KLBN11",
    "MRVE3", "PETR3", "PETR4", "PRIO3", "RECV3", "SLCE3", "SMTO3",
    "SUZB3", "USIM5", "VALE3",
}

B3_TARGET_ALIAS_TICKERS = {
    "ALUP11": ("ALUP4", "ALUP3"),
    "BPAC11": ("BPAC5", "BPAC3"),
    "KLBN11": ("KLBN4", "KLBN3"),
    "SANB11": ("SANB4", "SANB3"),
    "SAPR11": ("SAPR4", "SAPR3"),
    "TAEE11": ("TAEE4", "TAEE3"),
}

B3_SECTOR_CATALYSTS = {
    "Bancos": "ROE, crédito, dividendos e normalização de provisões",
    "Construção": "queda de juros, velocidade de vendas e geração de caixa",
    "Educação": "captação, retenção, inadimplência menor e desalavancagem",
    "Energia": "preço do petróleo, produção, dividendos e disciplina de capex",
    "Mineração": "minério de ferro, China, dividendos e disciplina de capital",
    "Saúde": "sinistralidade, ocupação, margem e desalavancagem",
    "Siderurgia": "ciclo de aço, China, custo de minério e câmbio",
    "Utilidades": "tarifas, dividendos, regulação e queda de juros",
    "Varejo": "queda de juros, margem bruta, crédito e consumo",
}
B3_SECTOR_RISKS = {
    "Bancos": "inadimplência, crédito e pressão regulatória",
    "Construção": "custo de obra, distratos, estoque e ciclo imobiliário",
    "Educação": "regulação, evasão, competição e inadimplência",
    "Energia": "commodity, governança, capex e intervenção estatal",
    "Mineração": "China, minério, passivos ambientais e ciclo de commodities",
    "Saúde": "sinistralidade, alavancagem, regulação e integração",
    "Siderurgia": "ciclo global, China, câmbio e excesso de oferta",
    "Utilidades": "regulação, revisão tarifária e alavancagem",
    "Varejo": "competição, crédito, margem e consumo fraco",
}

CANDIDATE_TARGETS = {
    "COGN3": "N/D",
    "MRVE3": "N/D",
    "YDUQ3": "N/D",
    "CYRE3": "N/D",
    "GMAT3": "R$ 6,93 (6 anal.)",
    "TOTS3": "R$ 49,75 (12 anal.)",
    "VIVA3": "R$ 34,00 (13 anal.)",
    "SUZB3": "R$ 65,58 (16 anal.)",
    "POMO4": "R$ 9,13 (9 anal.)",
    "CHTR": "N/D",
    "PDD": "N/D",
    "TCOM": "N/D",
    "ADBE": "N/D",
    "JD": "N/D",
    "TME": "N/D",
    "TAL": "N/D",
    "FUTU": "N/D",
    "BABA": "N/D",
    "CRM": "N/D",
    "CHWY": "N/D",
    "BILL": "N/D",
    "RBLX": "N/D",
    "FMC": "N/D",
}

CANDIDATE_SYMBOLS = {
    "COGN3": "COGN3.SA",
    "MRVE3": "MRVE3.SA",
    "YDUQ3": "YDUQ3.SA",
    "CYRE3": "CYRE3.SA",
    "TOTS3": "TOTS3.SA",
    "CHTR": "CHTR",
    "PDD": "PDD",
    "TCOM": "TCOM",
    "ADBE": "ADBE",
    "JD": "JD",
    "TME": "TME",
    "TAL": "TAL",
    "FUTU": "FUTU",
    "BABA": "BABA",
    "CRM": "CRM",
    "CHWY": "CHWY",
    "BILL": "BILL",
    "RBLX": "RBLX",
    "FMC": "FMC",
}

CANDIDATE_BUY_IN_ANALYSIS = {
    "COGN3": "Comprar so com margem e caixa melhorando.",
    "MRVE3": "Entrada parcial; juros e caixa precisam ajudar.",
    "YDUQ3": "Comprar em fraqueza se inadimplencia cair.",
    "CYRE3": "Comprar no desconto; vigiar margem e vendas.",
    "TOTS3": "Comprar so em pullback; valuation exige crescimento.",
    "CHTR": "Comprar se FCF pagar divida com folga.",
    "PDD": "Comprar se Temu crescer sem destruir margem.",
    "TCOM": "Comprar se viagens China seguirem fortes.",
    "ADBE": "Comprar se IA reacelerar receita e margem.",
    "JD": "Comprar so com margem de seguranca.",
    "TME": "Comprar se pagantes e ARPU seguirem subindo.",
    "TAL": "Compra tática; risco regulatorio precisa cair.",
    "FUTU": "Entrada por etapas; depende de mercado forte.",
    "BABA": "Comprar se cloud e recompras destravarem valor.",
    "BILL": "Entrada pequena; esperar retomada de crescimento.",
}

CANDIDATE_BUY_IN_DISCOUNT = {
    "COGN3": 0.15,
    "MRVE3": 0.14,
    "YDUQ3": 0.14,
    "CYRE3": 0.10,
    "TOTS3": 0.10,
    "CHTR": 0.15,
    "PDD": 0.12,
    "TCOM": 0.12,
    "ADBE": 0.10,
    "JD": 0.12,
    "TME": 0.14,
    "TAL": 0.14,
    "FUTU": 0.14,
    "BABA": 0.12,
    "BILL": 0.15,
}

CANDIDATE_REQUIRED_UPSIDE = {
    "COGN3": 0.45,
    "MRVE3": 0.42,
    "YDUQ3": 0.42,
    "CYRE3": 0.34,
    "TOTS3": 0.30,
    "CHTR": 0.38,
    "PDD": 0.35,
    "TCOM": 0.38,
    "ADBE": 0.28,
    "JD": 0.35,
    "TME": 0.40,
    "TAL": 0.40,
    "FUTU": 0.40,
    "BABA": 0.38,
    "BILL": 0.42,
}

NS = {
    "s": "http://schemas.xmlsoap.org/soap/envelope/",
    "m": "http://schemas.microsoft.com/exchange/services/2006/messages",
    "t": "http://schemas.microsoft.com/exchange/services/2006/types",
}


def keychain_password():
    env_password = os.getenv("EXCHANGE_APP_PASSWORD") or os.getenv("EXCHANGE_PASSWORD")
    if env_password:
        return env_password

    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            ACCOUNT,
            "-s",
            SERVICE,
            "-w",
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Senha nao encontrada no Keychain para chief-of-staff-exchange.")
    return result.stdout.rstrip("\n")


def ews_request(password, body_xml):
    envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
  <s:Header>
    <t:RequestServerVersion Version="Exchange2013" />
  </s:Header>
  <s:Body>
    {body_xml}
  </s:Body>
</s:Envelope>"""
    token = base64.b64encode(f"{ACCOUNT}:{password}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(EWS_URL, data=envelope.encode("utf-8"), method="POST")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "text/xml; charset=utf-8")
    req.add_header("Accept", "text/xml")
    req.add_header("User-Agent", "ChiefOfStaffDigital/1.0")
    last_exc = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"EWS HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"EWS connection failed after retries: {last_exc}") from last_exc


def text(node, path, default=""):
    found = node.find(path, NS)
    return found.text if found is not None and found.text is not None else default


def find_recent_emails(password, limit=250):
    body = f"""
<m:FindItem Traversal="Shallow">
  <m:ItemShape>
    <t:BaseShape>Default</t:BaseShape>
    <t:AdditionalProperties>
      <t:FieldURI FieldURI="item:TextBody" />
      <t:FieldURI FieldURI="message:From" />
      <t:FieldURI FieldURI="message:IsRead" />
      <t:FieldURI FieldURI="item:DateTimeReceived" />
      <t:FieldURI FieldURI="item:Categories" />
      <t:FieldURI FieldURI="item:Importance" />
    </t:AdditionalProperties>
  </m:ItemShape>
  <m:IndexedPageItemView MaxEntriesReturned="{limit}" Offset="0" BasePoint="Beginning" />
  <m:ParentFolderIds>
    <t:DistinguishedFolderId Id="inbox" />
  </m:ParentFolderIds>
  <m:SortOrder>
    <t:FieldOrder Order="Descending">
      <t:FieldURI FieldURI="item:DateTimeReceived" />
    </t:FieldOrder>
  </m:SortOrder>
</m:FindItem>"""
    root = ET.fromstring(ews_request(password, body))
    items = []
    for msg in root.findall(".//t:Message", NS):
        sender = text(msg, ".//t:From/t:Mailbox/t:Name")
        sender_email = text(msg, ".//t:From/t:Mailbox/t:EmailAddress")
        subject = text(msg, "t:Subject", "(sem assunto)").strip() or "(sem assunto)"
        body_text = text(msg, "t:TextBody").strip()
        received = parse_ews_time(text(msg, "t:DateTimeReceived"))
        items.append(
            {
                "item_id": msg.find("t:ItemId", NS).attrib.get("Id", "") if msg.find("t:ItemId", NS) is not None else "",
                "change_key": msg.find("t:ItemId", NS).attrib.get("ChangeKey", "") if msg.find("t:ItemId", NS) is not None else "",
                "subject": subject,
                "sender": sender or sender_email or "(sem remetente)",
                "sender_email": sender_email,
                "received": received,
                "is_read": text(msg, "t:IsRead", "true").lower() == "true",
                "importance": text(msg, "t:Importance", "Normal"),
                "body": normalize_ws(body_text),
            }
        )
    return items


def find_calendar_today(password, day):
    start = dt.datetime.combine(day, dt.time.min, TIMEZONE).astimezone(dt.timezone.utc)
    end = dt.datetime.combine(day, dt.time.max, TIMEZONE).astimezone(dt.timezone.utc)
    body = f"""
<m:FindItem Traversal="Shallow">
  <m:ItemShape>
    <t:BaseShape>Default</t:BaseShape>
    <t:AdditionalProperties>
      <t:FieldURI FieldURI="calendar:Start" />
      <t:FieldURI FieldURI="calendar:End" />
      <t:FieldURI FieldURI="calendar:Location" />
      <t:FieldURI FieldURI="calendar:IsAllDayEvent" />
      <t:FieldURI FieldURI="calendar:Organizer" />
    </t:AdditionalProperties>
  </m:ItemShape>
  <m:CalendarView StartDate="{start.isoformat().replace('+00:00', 'Z')}"
                  EndDate="{end.isoformat().replace('+00:00', 'Z')}" />
  <m:ParentFolderIds>
    <t:DistinguishedFolderId Id="calendar" />
  </m:ParentFolderIds>
</m:FindItem>"""
    root = ET.fromstring(ews_request(password, body))
    events = []
    for appt in root.findall(".//t:CalendarItem", NS):
        start_dt = parse_ews_time(text(appt, "t:Start"))
        end_dt = parse_ews_time(text(appt, "t:End"))
        events.append(
            {
                "subject": text(appt, "t:Subject", "(sem titulo)").strip() or "(sem titulo)",
                "start": start_dt,
                "end": end_dt,
                "location": text(appt, "t:Location", "").strip(),
                "all_day": text(appt, "t:IsAllDayEvent", "false").lower() == "true",
                "organizer": text(appt, ".//t:Organizer/t:Mailbox/t:Name", "").strip(),
            }
        )
    return sorted(events, key=lambda event: event["start"] or dt.datetime.max.replace(tzinfo=TIMEZONE))


def find_all_folders(password):
    body = """
<m:FindFolder Traversal="Deep">
  <m:FolderShape>
    <t:BaseShape>Default</t:BaseShape>
  </m:FolderShape>
  <m:ParentFolderIds>
    <t:DistinguishedFolderId Id="msgfolderroot" />
  </m:ParentFolderIds>
</m:FindFolder>"""
    root = ET.fromstring(ews_request(password, body))
    folders = [{"name": "Inbox", "id": None, "distinguished": "inbox"}]
    for folder in root.findall(".//t:Folder", NS):
        folder_id = folder.find("t:FolderId", NS)
        if folder_id is not None:
            folders.append(
                {
                    "name": text(folder, "t:DisplayName"),
                    "id": folder_id.attrib.get("Id", ""),
                    "change_key": folder_id.attrib.get("ChangeKey", ""),
                }
            )
    return folders


def find_billfish_summary_items(password, max_results=2):
    return find_billfish_items_by_subject_terms(
        password,
        ["Resumo Carteira"],
        max_results=max_results,
    )


def find_billfish_acomp_items(password, max_results=1):
    return find_billfish_items_by_subject_terms(
        password,
        ["Carteira Diária", "Carteira Diaria", "Relatório da Carteira Diária", "Relatorio da Carteira Diaria"],
        max_results=max_results,
    )


def find_billfish_items_by_subject_terms(password, subject_terms, max_results=2):
    results = []
    for term in subject_terms:
        results.extend(find_billfish_items_by_subject(password, term, max_results=max_results))
    deduped = {}
    for item in results:
        deduped[item["id"]] = item
    return sorted(
        deduped.values(),
        key=lambda item: item["received"] or dt.datetime.min.replace(tzinfo=TIMEZONE),
        reverse=True,
    )[:max_results]


def find_billfish_items_by_subject(password, subject_term=None, max_results=2):
    results = []
    folders = [
        folder
        for folder in prioritize_billfish_folders(find_all_folders(password))
        if billfish_folder_is_candidate(folder)
    ]
    for folder in folders:
        parent = (
            '<t:DistinguishedFolderId Id="inbox" />'
            if folder.get("distinguished")
            else f'<t:FolderId Id="{html.escape(folder["id"])}" />'
        )
        body = f"""
<m:FindItem Traversal="Shallow">
  <m:ItemShape>
    <t:BaseShape>Default</t:BaseShape>
    <t:AdditionalProperties>
      <t:FieldURI FieldURI="item:DateTimeReceived" />
      <t:FieldURI FieldURI="item:HasAttachments" />
    </t:AdditionalProperties>
  </m:ItemShape>
  <m:IndexedPageItemView MaxEntriesReturned="{min(max(max_results * 2, 10), 50)}" Offset="0" BasePoint="Beginning" />
  <m:Restriction>
    {billfish_subject_restriction(subject_term)}
  </m:Restriction>
  <m:ParentFolderIds>{parent}</m:ParentFolderIds>
  <m:SortOrder>
    <t:FieldOrder Order="Descending">
      <t:FieldURI FieldURI="item:DateTimeReceived" />
    </t:FieldOrder>
  </m:SortOrder>
</m:FindItem>"""
        try:
            root = ET.fromstring(ews_request(password, body))
        except Exception:
            continue
        for msg in root.findall(".//t:Message", NS):
            item_id = msg.find("t:ItemId", NS)
            subject = text(msg, "t:Subject")
            received = parse_ews_time(text(msg, "t:DateTimeReceived"))
            if item_id is not None:
                results.append(
                    {
                        "subject": subject,
                        "received": received,
                        "id": item_id.attrib.get("Id", ""),
                        "folder": folder["name"],
                    }
                )
        if subject_term and results:
            break
        if len(results) >= max_results:
            break
    deduped = {}
    for item in results:
        deduped[item["id"]] = item
    return sorted(
        deduped.values(),
        key=lambda item: item["received"] or dt.datetime.min.replace(tzinfo=TIMEZONE),
        reverse=True,
    )[:max_results]


def billfish_subject_restriction(subject_term=None):
    billfish_contains = """
      <t:Contains ContainmentMode="Substring" ContainmentComparison="IgnoreCase">
        <t:FieldURI FieldURI="item:Subject" />
        <t:Constant Value="BILLFISH FIA" />
      </t:Contains>"""
    if not subject_term:
        return billfish_contains
    return f"""
    <t:And>
      <t:Contains ContainmentMode="Substring" ContainmentComparison="IgnoreCase">
        <t:FieldURI FieldURI="item:Subject" />
        <t:Constant Value="{html.escape(subject_term)}" />
      </t:Contains>
      {billfish_contains}
    </t:And>"""


def billfish_folder_is_candidate(folder):
    name = (folder.get("name") or "").lower()
    return any(
        term in name
        for term in [
            "inbox",
            "entrada",
            "investimentos",
            "bancos",
            "btg",
            "alta atencao",
            "alta atenção",
            "chief of staff",
            "itens excluídos",
            "itens excluidos",
            "deleted",
        ]
    )


def prioritize_billfish_folders(folders):
    preferred_terms = [
        "inbox",
        "entrada",
        "investimentos",
        "bancos",
        "btg",
        "alta atencao",
        "alta atenção",
        "chief of staff",
        "itens excluídos",
        "itens excluidos",
        "deleted",
    ]

    def score(folder):
        name = (folder.get("name") or "").lower()
        for idx, term in enumerate(preferred_terms):
            if term in name:
                return idx
        return len(preferred_terms)

    return sorted(folders, key=score)


def get_item_attachments(password, item_id, allowed_suffixes=(".pdf",)):
    body = f"""
<m:GetItem>
  <m:ItemShape>
    <t:BaseShape>AllProperties</t:BaseShape>
  </m:ItemShape>
  <m:ItemIds>
    <t:ItemId Id="{html.escape(item_id)}" />
  </m:ItemIds>
</m:GetItem>"""
    root = ET.fromstring(ews_request(password, body))
    attachments = []
    for att in root.findall(".//t:FileAttachment", NS):
        att_id = att.find("t:AttachmentId", NS)
        name = text(att, "t:Name")
        if att_id is not None and (not allowed_suffixes or name.lower().endswith(tuple(allowed_suffixes))):
            attachments.append({"name": name, "id": att_id.attrib.get("Id", "")})
    return attachments


def download_attachment_bytes(password, attachment_id):
    body = f"""
<m:GetAttachment>
  <m:AttachmentShape />
  <m:AttachmentIds>
    <t:AttachmentId Id="{html.escape(attachment_id)}" />
  </m:AttachmentIds>
</m:GetAttachment>"""
    root = ET.fromstring(ews_request(password, body))
    content = text(root, ".//t:Content")
    return base64.b64decode(content) if content else b""


def pdf_reader_class():
    try:
        from pypdf import PdfReader

        return PdfReader
    except ModuleNotFoundError:
        bundled_site = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages"
        if bundled_site.exists():
            sys.path.append(str(bundled_site))
            from pypdf import PdfReader

            return PdfReader
        raise


def fetch_billfish_snapshot(password):
    btg_snapshot = fetch_billfish_snapshot_from_btg_pdf(password)
    if btg_snapshot.get("available"):
        return btg_snapshot

    aws_snapshot = fetch_billfish_snapshot_from_aws_summary()
    if aws_snapshot.get("available"):
        aws_snapshot["btg_error"] = btg_snapshot.get("error")
        return aws_snapshot
    return {
        "available": False,
        "error": f"{btg_snapshot.get('error', 'BTG indisponivel')} | {aws_snapshot.get('error', 'cache indisponivel')}",
    }


def fetch_billfish_snapshot_from_btg_pdf(password):
    try:
        PdfReader = pdf_reader_class()

        items = find_billfish_summary_items(password, max_results=8)
        parsed = []
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for item in items:
                for attachment in get_item_attachments(password, item["id"]):
                    data = download_attachment_bytes(password, attachment["id"])
                    if not data:
                        continue
                    path = tmp / attachment["name"]
                    path.write_bytes(data)
                    pdf_text = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
                    parsed_item = parse_billfish_pdf_text(pdf_text)
                    if parsed_item:
                        parsed_item["source"] = attachment["name"]
                        parsed_item["received"] = item.get("received")
                        parsed_item["email_subject"] = item.get("subject")
                        parsed_item["folder"] = item.get("folder")
                        parsed.append(parsed_item)
                        break
        if not parsed:
            return {"available": False, "error": "relatorio nao encontrado"}
        parsed = sorted(parsed, key=billfish_report_sort_key, reverse=True)
        latest = parsed[0]
        previous = next((report for report in parsed[1:] if report.get("date") != latest.get("date")), None)
        if previous is None:
            previous = parsed[1] if len(parsed) > 1 else None
        if previous and latest.get("quota") is not None and previous.get("quota"):
            latest["quota_change_calc"] = (latest["quota"] / previous["quota"] - 1) * 100
        else:
            latest["quota_change_calc"] = None
        performance = fetch_billfish_btg_performance_with_timeout(password, PdfReader, target_date=latest.get("date"))
        if not performance:
            performance = (fetch_billfish_snapshot_from_aws_summary().get("performance") or {})
        return {
            "available": True,
            "latest": latest,
            "previous": previous,
            "performance": performance,
            "source": "BTG PDF",
        }
    except Exception as exc:
        return {"available": False, "error": f"BTG PDF/email: {type(exc).__name__}: {exc}"}


def parse_billfish_report_date(value):
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def billfish_report_sort_key(report):
    report_date = parse_billfish_report_date(report.get("date")) or dt.date.min
    received = report.get("received")
    if received is None:
        received = dt.datetime.min.replace(tzinfo=TIMEZONE)
    elif received.tzinfo is None:
        received = received.replace(tzinfo=TIMEZONE)
    return (report_date, received, report.get("source") or "")


class BillfishPerformanceTimeout(Exception):
    pass


def fetch_billfish_btg_performance_with_timeout(password, pdf_reader_cls, target_date=None, timeout_seconds=25):
    if not hasattr(signal, "SIGALRM"):
        return fetch_billfish_btg_performance(password, pdf_reader_cls, target_date=target_date)

    previous_handler = signal.getsignal(signal.SIGALRM)

    def timeout_handler(signum, frame):
        raise BillfishPerformanceTimeout()

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)
    try:
        return fetch_billfish_btg_performance(password, pdf_reader_cls, target_date=target_date)
    except BillfishPerformanceTimeout:
        return {}
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def fetch_billfish_snapshot_from_aws_summary():
    for path in latest_billfish_summary_files():
        try:
            parsed = parse_billfish_summary_snapshot(path)
        except Exception as exc:
            return {"available": False, "error": f"AWS summary parse: {type(exc).__name__}: {exc}"}
        if parsed.get("available"):
            return parsed
    return {"available": False, "error": "AWS summary indisponivel"}


def latest_billfish_summary_files():
    candidates = list(OUT_DIR.glob("*summary-*.txt"))
    candidates.extend(OUT_DIR.glob("resumo-manha-*.txt"))
    return sorted(
        {path for path in candidates if path.is_file()},
        key=billfish_summary_sort_key,
        reverse=True,
    )


def billfish_summary_sort_key(path):
    name = path.name
    match = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    date_part = match.group(1) if match else ""
    period_rank = 0
    if name.startswith("night-summary-"):
        period_rank = 4
    elif name.startswith("late-summary-"):
        period_rank = 3
    elif name.startswith("lunch-summary-"):
        period_rank = 2
    elif name.startswith("morning-summary-") or name.startswith("resumo-manha-"):
        period_rank = 1
    return (date_part, period_rank, name)


def parse_billfish_summary_snapshot(path):
    line = extract_billfish_summary_line(path.read_text(encoding="utf-8", errors="replace"))
    if not line:
        return {"available": False, "error": f"Billfish nao encontrado em {path.name}"}
    if line.startswith("- "):
        line = line[2:]

    pattern = re.compile(
        r"^(?:Status|Posicao)\s+(?P<date>\d{2}/\d{2}/\d{4})\s+\|\s+"
        r"daily change\s+(?P<daily>[^|]+?)\s+\|\s+"
        r"net worth\s+(?P<pl>R\$\s*[^|]+?)\s+\|\s+"
        r"net worth change\s+(?P<pl_change>[^|]+?)\s+\|\s+"
        r"fonte\s+(?P<source>[^|]+?)"
        r"(?:\s+\|\s+Month:\s+Billfish\s+(?P<billfish_month>[^,]+),\s+"
        r"Ibov\s+(?P<ibov_month>[^,]+),\s+"
        r"S&P 500\s+(?P<sp500_month>[^,]+),\s+"
        r"CDI\s+(?P<cdi_month>[^|]+)\s+\|\s+"
        r"Year:\s+Billfish\s+(?P<billfish_year>[^,]+),\s+"
        r"Ibov\s+(?P<ibov_year>[^,]+),\s+"
        r"S&P 500\s+(?P<sp500_year>[^,]+),\s+"
        r"CDI\s+(?P<cdi_year>[^,]+),\s+"
        r"IPCA 12M\s+(?P<ipca_12m>.+))?$"
    )
    match = pattern.match(line.strip())
    if not match:
        return {"available": False, "error": f"linha Billfish invalida em {path.name}"}

    source_name = match.group("source").strip()
    latest = {
        "date": match.group("date"),
        "pl": parse_summary_brl(match.group("pl")),
        "pl_change": parse_summary_signed_brl(match.group("pl_change")),
        "daily_return_pct": parse_summary_pct(match.group("daily")),
        "quota_change_calc": None,
        "source": source_name,
    }
    performance = {
        "date": match.group("date"),
        "billfish_month_pct": parse_summary_pct(match.group("billfish_month")),
        "ibov_month_pct": parse_summary_pct(match.group("ibov_month")),
        "sp500_month_pct": parse_summary_pct(match.group("sp500_month")),
        "cdi_month_pct": parse_summary_pct(match.group("cdi_month")),
        "billfish_year_pct": parse_summary_pct(match.group("billfish_year")),
        "ibov_year_pct": parse_summary_pct(match.group("ibov_year")),
        "sp500_year_pct": parse_summary_pct(match.group("sp500_year")),
        "cdi_year_pct": parse_summary_pct(match.group("cdi_year")),
        "ipca_12m_pct": parse_summary_pct(match.group("ipca_12m")),
    }
    if not any(value is not None for key, value in performance.items() if key != "date"):
        performance = {}
    return {
        "available": True,
        "latest": latest,
        "previous": None,
        "performance": performance,
        "source": f"AWS summary ({path.name})",
        "summary_file": path.name,
    }


def extract_billfish_summary_line(text):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "Billfish FIA" and index + 1 < len(lines):
            return lines[index + 1].strip()
    return None


def parse_summary_pct(value):
    cleaned = (value or "").split(" / ", 1)[0].strip()
    if cleaned in {"", "-", "N/D", "retorno indisponivel"}:
        return None
    try:
        return float(cleaned.replace("%", "").replace(",", "."))
    except ValueError:
        return None


def parse_summary_brl(value):
    cleaned = (value or "").replace("R$", "").strip()
    return parse_ptbr_number(cleaned)


def parse_summary_signed_brl(value):
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    sign = -1 if cleaned.startswith("-") else 1
    number = parse_summary_brl(cleaned.lstrip("+-").strip())
    return None if number is None else sign * number


def fetch_brokerage_notes_snapshot(password):
    try:
        PdfReader = pdf_reader_class()
        items = find_brokerage_note_items(password, max_results=6)
        if not items:
            return {"available": False, "error": "email com Notas de corretagem nao encontrado"}

        seen_messages = set()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for item in items:
                message_key = (item.get("subject"), item.get("received"))
                if message_key in seen_messages:
                    continue
                seen_messages.add(message_key)

                notes = []
                for attachment in get_item_attachments(password, item["id"]):
                    data = download_attachment_bytes(password, attachment["id"])
                    if not data:
                        continue
                    path = tmp / sanitize_attachment_filename(attachment["name"])
                    path.write_bytes(data)
                    pdf_text = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
                    parsed = parse_brokerage_note_pdf_text(pdf_text, attachment["name"], item)
                    if parsed:
                        notes.append(parsed)
                if notes:
                    return build_brokerage_notes_snapshot(item, notes)
        return {"available": False, "error": "anexo de nota nao parseado"}
    except Exception as exc:
        return {"available": False, "error": f"Notas de corretagem: {type(exc).__name__}: {exc}"}


def find_brokerage_note_items(password, max_results=6):
    results = []
    folders = prioritize_brokerage_note_folders(find_all_folders(password))
    for folder in folders:
        parent = (
            '<t:DistinguishedFolderId Id="inbox" />'
            if folder.get("distinguished")
            else f'<t:FolderId Id="{html.escape(folder["id"])}" />'
        )
        body = f"""
<m:FindItem Traversal="Shallow">
  <m:ItemShape>
    <t:BaseShape>Default</t:BaseShape>
    <t:AdditionalProperties>
      <t:FieldURI FieldURI="item:DateTimeReceived" />
      <t:FieldURI FieldURI="item:HasAttachments" />
    </t:AdditionalProperties>
  </m:ItemShape>
  <m:IndexedPageItemView MaxEntriesReturned="20" Offset="0" BasePoint="Beginning" />
  <m:Restriction>
    <t:Contains ContainmentMode="Substring" ContainmentComparison="IgnoreCase">
      <t:FieldURI FieldURI="item:Subject" />
      <t:Constant Value="Notas de corretagem" />
    </t:Contains>
  </m:Restriction>
  <m:ParentFolderIds>{parent}</m:ParentFolderIds>
  <m:SortOrder>
    <t:FieldOrder Order="Descending">
      <t:FieldURI FieldURI="item:DateTimeReceived" />
    </t:FieldOrder>
  </m:SortOrder>
</m:FindItem>"""
        try:
            root = ET.fromstring(ews_request(password, body))
        except Exception:
            continue
        for msg in root.findall(".//t:Message", NS):
            item_id = msg.find("t:ItemId", NS)
            if item_id is None:
                continue
            results.append(
                {
                    "subject": text(msg, "t:Subject"),
                    "received": parse_ews_time(text(msg, "t:DateTimeReceived")),
                    "id": item_id.attrib.get("Id", ""),
                    "folder": folder["name"],
                }
            )
        folder_name = (folder.get("name") or "").lower()
        if results and ("inbox" in folder_name or "caixa de entrada" in folder_name):
            break
        if len(results) >= max_results:
            break

    deduped = {}
    for item in results:
        key = (item.get("subject"), item.get("received"))
        deduped[key] = item
    return sorted(
        deduped.values(),
        key=lambda item: item["received"] or dt.datetime.min.replace(tzinfo=TIMEZONE),
        reverse=True,
    )[:max_results]


def prioritize_brokerage_note_folders(folders):
    preferred_terms = [
        "inbox",
        "caixa de entrada",
        "investimentos",
        "bancos",
        "btg",
        "chief of staff",
        "itens excluídos",
        "itens excluidos",
        "deleted",
    ]

    def score(folder):
        name = (folder.get("name") or "").lower()
        for idx, term in enumerate(preferred_terms):
            if term in name:
                return idx
        return len(preferred_terms)

    return sorted(folders, key=score)


def sanitize_attachment_filename(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name or "attachment.pdf")


def build_brokerage_notes_snapshot(item, notes):
    trades = []
    total_traded = 0.0
    net_total = 0.0
    trade_date = brokerage_date_from_subject(item.get("subject", ""))
    note_types = []
    attachments = []
    financial_summary = []
    for note in notes:
        note_types.append(note.get("type", "Nota"))
        attachments.append(note.get("attachment", ""))
        trade_date = trade_date or note.get("trade_date")
        total_traded += note.get("total_traded") or 0
        net_total += note.get("net_total") or 0
        trades.extend(note.get("trades") or [])
        financial_summary.extend(note.get("financial_summary") or [])
    return {
        "available": True,
        "subject": item.get("subject", ""),
        "received": item.get("received"),
        "folder": item.get("folder", ""),
        "trade_date": trade_date,
        "note_types": sorted(set(filter(None, note_types))),
        "attachments": [name for name in attachments if name],
        "total_traded": total_traded,
        "net_total": net_total,
        "trades": trades,
        "financial_summary": financial_summary,
        "source": "BTG PDF",
    }


def parse_brokerage_note_pdf_text(pdf_text, attachment_name, item):
    clean = normalize_ws(pdf_text)
    if "NOTA DE EMPRÉSTIMO" in pdf_text or "NOTA DE EMPRESTIMO" in pdf_text:
        return parse_stockloan_note_pdf_text(pdf_text, attachment_name, item)
    if "NOTA DE CORRETAGEM" in pdf_text:
        return parse_spot_brokerage_note_pdf_text(pdf_text, attachment_name, item)
    return None


def parse_stockloan_note_pdf_text(pdf_text, attachment_name, item):
    trade_date = brokerage_date_from_subject(item.get("subject", ""))
    note_number = regex_text(pdf_text, r"Número da Nota\s+(\d+)")
    side = regex_text(pdf_text, r"Lado\s+([^\n]+)")
    trades = []
    for chunk in stockloan_operation_chunks(pdf_text):
        contract = regex_text(chunk, r"Contrato:\s*([^\n]+)")
        ticker = regex_text(chunk, r"Papel:\s*([A-Z0-9]+)")
        tax = regex_text(chunk, r"Taxa:\s*([^\n]+)")
        quantity = parse_int_number(regex_text(chunk, r"Qtd\.?\s+Liquidação\s+([\d.]+)"))
        settlement_value = parse_brl_number(regex_text(chunk, r"Valor Liquidação:\s*R\$\s*([\d.]+,\d{2})"))
        remuneration = parse_brl_number(regex_text(chunk, r"Remuneração:\s*R\$\s*([\d.]+,\d{2})"))
        net_value = parse_brl_number(regex_text(chunk, r"Valor Líquido\s+R\$\s*([\d.]+,\d{2})"))
        trades.append(
            {
                "type": "Aluguel",
                "side": side or "Doador/Tomador",
                "asset": ticker or "-",
                "quantity": quantity,
                "price": tax or "-",
                "value": settlement_value,
                "net": net_value if net_value is not None else remuneration,
                "detail": f"Contrato {contract}" if contract else "Nota de emprestimo",
            }
        )
    if not trades:
        trades.append(
            {
                "type": "Aluguel",
                "side": side or "Doador/Tomador",
                "asset": regex_text(pdf_text, r"Papel:\s*([A-Z0-9]+)") or "-",
                "quantity": parse_int_number(regex_text(pdf_text, r"Qtd\.?\s+Liquidação\s+([\d.]+)")),
                "price": regex_text(pdf_text, r"Taxa:\s*([^\n]+)") or "-",
                "value": parse_brl_number(regex_text(pdf_text, r"Valor Liquidação:\s*R\$\s*([\d.]+,\d{2})")),
                "net": parse_brl_number(regex_text(pdf_text, r"Valor Líquido\s+R\$\s*([\d.]+,\d{2})")),
                "detail": "Nota de emprestimo",
            }
        )
    financial_summary = parse_stockloan_financial_summary(pdf_text)
    return {
        "type": "Aluguel",
        "attachment": attachment_name,
        "trade_date": trade_date,
        "note_number": note_number,
        "total_traded": sum((trade.get("value") or 0) for trade in trades),
        "net_total": sum((trade.get("net") or 0) for trade in trades),
        "trades": trades,
        "financial_summary": financial_summary,
    }


def stockloan_operation_chunks(pdf_text):
    chunks = []
    current = []
    for raw_line in (pdf_text or "").splitlines():
        line = normalize_ws(raw_line)
        if not line:
            continue
        if line.startswith("Contrato:"):
            if current:
                chunks.append("\n".join(current))
            current = [line]
            continue
        if current:
            if line.startswith("Resumo financeiro"):
                chunks.append("\n".join(current))
                current = []
                break
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


def parse_stockloan_financial_summary(pdf_text):
    items = []
    gross = money_after_label(pdf_text, "Valor Bruto")
    emoluments = money_after_label(pdf_text, "Emolumentos")
    tax = money_after_label(pdf_text, "I.R.R.F.")
    execution = money_after_label(pdf_text, "Execução") or money_after_label(pdf_text, "Execucao")
    clearing = money_after_label(pdf_text, "Clearing")
    net = money_after_label(pdf_text, "Valor líquido") or money_after_label(pdf_text, "Valor liquido")
    for label, value, signed in [
        ("Gross", gross, False),
        ("Emoluments", -emoluments if emoluments is not None else None, True),
        ("IRRF", -tax if tax is not None else None, True),
        ("Execution", -execution if execution is not None else None, True),
        ("Clearing", -clearing if clearing is not None else None, True),
        ("Net", net, True),
    ]:
        if value is not None:
            items.append(financial_summary_item(label, value, signed=signed))
    return items


def parse_spot_brokerage_note_pdf_text(pdf_text, attachment_name, item):
    trade_date = regex_text(pdf_text, r"(\d{2}/\d{2}/\d{4})\s+Data pregão") or brokerage_date_from_subject(item.get("subject", ""))
    note_number = regex_text(pdf_text, r"NOTA DE CORRETAGEM\s+(\d+)")
    trades = []
    in_trades = False
    for raw_line in pdf_text.splitlines():
        line = normalize_ws(raw_line)
        if not line:
            continue
        if "Negócios realizados" in line or "Negocios realizados" in line:
            in_trades = True
            continue
        if "Resumo dos Negócios" in line or "Resumo dos Negocios" in line:
            break
        if not in_trades:
            continue
        trade = parse_spot_trade_line(line)
        if trade:
            trades.append(trade)

    total_traded = (
        money_before_label(pdf_text, "Valor das operações")
        or money_before_label(pdf_text, "Valor das operacoes")
        or sum((trade.get("value") or 0) for trade in trades)
    )
    net_total = parse_final_spot_net_total(pdf_text)
    return {
        "type": "A Vista/Termo",
        "attachment": attachment_name,
        "trade_date": trade_date,
        "note_number": note_number,
        "total_traded": total_traded or 0,
        "net_total": net_total or 0,
        "trades": trades,
        "financial_summary": parse_spot_financial_summary(pdf_text, net_total),
    }


def parse_spot_financial_summary(pdf_text, net_total):
    sales = money_before_label(pdf_text, "Vendas à vista") or money_before_label(pdf_text, "Vendas a vista")
    purchases = money_after_label(pdf_text, "Compras à vista") or money_after_label(pdf_text, "Compras a vista")
    operations_total = money_before_label(pdf_text, "Valor das operações") or money_before_label(pdf_text, "Valor das operacoes")
    operations_net = (
        money_before_label(pdf_text, "Valor líquido das operações")
        or money_before_label(pdf_text, "Valor liquido das operacoes")
    )
    liquidation_fee = money_before_label(pdf_text, "Taxa de liquidação/CCP") or money_before_label(pdf_text, "Taxa de liquidacao/CCP")
    emoluments = money_before_label(pdf_text, "Emolumentos")
    bovespa_total = money_before_label(pdf_text, "Total Bovespa / Soma")
    brokerage_expenses = money_after_label(pdf_text, "Total corretagem / Despesas")
    asset_transfer = money_after_label(pdf_text, "Taxa de Transferencia de Ativos")
    items = []
    for label, value, signed in [
        ("Sales", sales, False),
        ("Purchases", purchases, False),
        ("Operations", operations_total, False),
        ("Operations net", operations_net, True),
        ("Liquidation fee", -liquidation_fee if liquidation_fee is not None else None, True),
        ("Emoluments", -emoluments if emoluments is not None else None, True),
        ("Bovespa fees", -bovespa_total if bovespa_total is not None else None, True),
        ("Brokerage/expenses", -brokerage_expenses if brokerage_expenses is not None else None, True),
        ("Asset transfer", -asset_transfer if asset_transfer is not None else None, True),
        ("Final net", net_total, True),
    ]:
        if value is not None:
            items.append(financial_summary_item(label, value, signed=signed))
    return items


def financial_summary_item(label, value, signed=False):
    return {"label": label, "value": value, "signed": signed}


def parse_spot_trade_line(line):
    pattern = (
        r"^\S+\s+([CV])\s+(\S+)\s+([A-Z0-9]+)\s+"
        r"(?:[A-Z0-9./]+(?:\s+[A-Z0-9./]+)*\s+)?"
        r"([\d.]+)\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([CD])$"
    )
    match = re.match(pattern, line)
    if not match:
        return None
    side_code, market, asset, quantity, price, value, debit_credit = match.groups()
    return {
        "type": market,
        "side": "Compra" if side_code == "C" else "Venda",
        "asset": asset,
        "quantity": parse_int_number(quantity),
        "price": parse_brl_number(price),
        "value": parse_brl_number(value),
        "net": None,
        "detail": debit_credit,
    }


def parse_final_spot_net_total(pdf_text):
    match = re.search(r"Líquido para\s+\d{2}/\d{2}/\d{4}\s+([CD])\s*([\d.]+,\d{2})", pdf_text)
    if not match:
        match = re.search(r"Liquido para\s+\d{2}/\d{2}/\d{4}\s+([CD])\s*([\d.]+,\d{2})", pdf_text)
    if not match:
        return money_before_label(pdf_text, "Valor líquido das operações") or money_before_label(pdf_text, "Valor liquido das operacoes")
    value = parse_brl_number(match.group(2))
    return -value if match.group(1) == "D" else value


def brokerage_date_from_subject(subject):
    match = re.search(r"(\d{2}/\d{2}/\d{4})", subject or "")
    return match.group(1) if match else None


def regex_text(value, pattern):
    match = re.search(pattern, value or "", re.I)
    return normalize_ws(match.group(1)) if match else None


def money_before_label(text_value, label):
    pattern = r"([\d.]+,\d{2})\s*" + re.escape(label)
    match = re.search(pattern, text_value or "", re.I)
    return parse_brl_number(match.group(1)) if match else None


def money_after_label(text_value, label):
    pattern = re.escape(label) + r"\s*(?:R\$\s*)?([\d.]+,\d{2})"
    match = re.search(pattern, text_value or "", re.I)
    return parse_brl_number(match.group(1)) if match else None


def parse_brl_number(value):
    if value is None:
        return None
    cleaned = str(value).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int_number(value):
    if value is None:
        return None
    cleaned = re.sub(r"[^0-9-]", "", str(value))
    try:
        return int(cleaned)
    except ValueError:
        return None


def fetch_billfish_btg_performance(password, pdf_reader_cls, target_date=None):
    try:
        items = find_billfish_acomp_items(password, max_results=8)
        if not items:
            return {}
        parsed_reports = []
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for item in items:
                for attachment in get_item_attachments(password, item["id"]):
                    data = download_attachment_bytes(password, attachment["id"])
                    if not data:
                        continue
                    path = tmp / attachment["name"]
                    path.write_bytes(data)
                    pdf_text = "\n".join((page.extract_text() or "") for page in pdf_reader_cls(str(path)).pages)
                    parsed = parse_billfish_performance_pdf_text(pdf_text)
                    if parsed:
                        parsed["source"] = attachment["name"]
                        parsed["received"] = item.get("received")
                        parsed_reports.append(parsed)
                        break
        if not parsed_reports:
            return {}
        if target_date:
            for report in sorted(parsed_reports, key=billfish_report_sort_key, reverse=True):
                if report.get("date") == target_date:
                    return report
        return sorted(parsed_reports, key=billfish_report_sort_key, reverse=True)[0]
    except Exception:
        return {}
    return {}


def fetch_billfish_snapshot_from_maisretorno():
    url = "https://api.maisretorno.com/v3/funds/quotes/19366027000120"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://maisretorno.com/fundo/billfish-fif-acoes",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        quotes = [quote for quote in payload.get("quotes", []) if quote.get("c") and quote.get("p")]
        if len(quotes) < 2:
            return {"available": False, "error": "serie insuficiente na API"}
        latest = quotes[-1]
        previous = quotes[-2]
        latest_date = dt.datetime.fromtimestamp(latest["d"] / 1000, dt.timezone.utc)
        previous_date = dt.datetime.fromtimestamp(previous["d"] / 1000, dt.timezone.utc)
        latest_item = {
            "date": latest_date.strftime("%d/%m/%Y"),
            "pl": float(latest["p"]),
            "pl_change": float(latest["p"]) - float(previous["p"]),
            "quota": float(latest["c"]),
            "daily_return_pct": (float(latest["c"]) / float(previous["c"]) - 1) * 100,
            "quota_change_calc": (float(latest["c"]) / float(previous["c"]) - 1) * 100,
            "source": "Mais Retorno",
        }
        previous_item = {
            "date": previous_date.strftime("%d/%m/%Y"),
            "pl": float(previous["p"]),
            "quota": float(previous["c"]),
            "source": "Mais Retorno",
        }
        return {
            "available": True,
            "latest": latest_item,
            "previous": previous_item,
            "source": "Mais Retorno",
        }
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def parse_billfish_pdf_text(pdf_text):
    position = re.search(r"Posição:\s*(\d{2}/\d{2}/\d{4})", pdf_text)
    patrimonio = re.search(r"PATRIM[ÔO]NIO\s+([\d,]+\.\d{2})\s+\(?(-?[\d,]+\.\d{2})\)?", pdf_text)
    quota = re.search(r"COTA L[ÍI]QUIDA\s+([\d.]+)", pdf_text)
    rent = re.search(r"COTA\s+\(?(-?[\d.]+)\)?\s+\(?(-?[\d.]+)\)?\s+(-?[\d.]+)\s+(-?[\d.]+)", pdf_text)
    if not position or not patrimonio:
        return None
    pl_change_raw = patrimonio.group(2)
    is_negative_pl_change = "(" in patrimonio.group(0) and not pl_change_raw.startswith("-")
    return {
        "date": position.group(1),
        "pl": parse_us_number(patrimonio.group(1)),
        "pl_change": -parse_us_number(pl_change_raw) if is_negative_pl_change else parse_us_number(pl_change_raw),
        "quota": parse_us_number(quota.group(1)) if quota else None,
        "daily_return_pct": parse_signed_parenthetical(rent.group(1), pdf_text[pdf_text.find("Rentabilidades"):]) if rent else None,
    }


def parse_billfish_performance_pdf_text(pdf_text):
    position = re.search(r"Valor da Cota em\s+(\d{2}/\d{2}/\d{4})", pdf_text)
    if not position:
        position = re.search(r"(\d{2}/\d{2}/\d{4})\s+[\d,]+\.\d{2}\s+[\d.]+\s", pdf_text)
    position_date = position.group(1) if position else None
    row = None
    if position_date:
        row_pattern = (
            re.escape(position_date)
            + r"\s+[\d,]+\.\d{2}\s+[\d.]+\s+"
            + r"\(?(-?[\d,]+\.\d+)\)?\s+\(?(-?[\d,]+\.\d+)\)?\s+"
            + r"\(?(-?[\d,]+\.\d+)\)?\s+\(?(-?[\d,]+\.\d+)\)?\s+"
            + r"\(?(-?[\d,]+\.\d+)\)?\s+\(?(-?[\d,]+\.\d+)\)?"
        )
        row = re.search(row_pattern, pdf_text)
    if not row:
        return {}

    day_return = parse_signed_from_match(row.group(1), row.group(0))
    month_return = parse_signed_from_match(row.group(3), row.group(0))
    month_cdi_pct = parse_signed_from_match(row.group(4), row.group(0))
    year_return = parse_signed_from_match(row.group(5), row.group(0))
    year_cdi_pct = parse_signed_from_match(row.group(6), row.group(0))
    cdi_month = month_return / (month_cdi_pct / 100) if month_cdi_pct else None
    cdi_year = year_return / (year_cdi_pct / 100) if year_cdi_pct else None
    ibov = fetch_index_performance(position_date, "%5EBVSP", "Yahoo Finance ^BVSP") if position_date else {}
    sp500 = fetch_index_performance(position_date, "%5EGSPC", "Yahoo Finance ^GSPC") if position_date else {}
    return {
        "date": position_date,
        "billfish_month_pct": month_return,
        "billfish_year_pct": year_return,
        "cdi_month_pct": cdi_month,
        "cdi_year_pct": cdi_year,
        "ibov_month_pct": ibov.get("month_pct"),
        "ibov_year_pct": ibov.get("year_pct"),
        "ibov_source": ibov.get("source"),
        "sp500_month_pct": sp500.get("month_pct"),
        "sp500_year_pct": sp500.get("year_pct"),
        "sp500_source": sp500.get("source"),
        "ipca_12m_pct": fetch_ipca_12m_pct(),
    }


def parse_signed_from_match(value, context):
    number = parse_us_number(value)
    return -number if f"({value})" in context else number


def fetch_index_performance(reference_date, yahoo_symbol, source):
    try:
        ref = dt.datetime.strptime(reference_date, "%d/%m/%Y").date()
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=1y&interval=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        points = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()
            if date <= ref:
                points.append((date, float(close)))
        if len(points) < 2:
            return {}
        latest_date, latest_close = points[-1]
        month_start = dt.date(ref.year, ref.month, 1)
        year_start = dt.date(ref.year, 1, 1)
        month_base = last_close_before(points, month_start)
        year_base = last_close_before(points, year_start)
        return {
            "month_pct": (latest_close / month_base - 1) * 100 if month_base else None,
            "year_pct": (latest_close / year_base - 1) * 100 if year_base else None,
            "source": source,
        }
    except Exception:
        return {}


def last_close_before(points, date):
    candidates = [close for point_date, close in points if point_date < date]
    return candidates[-1] if candidates else None


def fetch_ipca_12m_pct():
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json"
    req = urllib.request.Request(url, headers={"User-Agent": "ChiefOfStaffDigital/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload:
            return None
        return float(str(payload[-1]["valor"]).replace(",", "."))
    except Exception:
        return None


def parse_us_number(value):
    return float(value.replace(",", ""))


def parse_signed_parenthetical(value, context):
    number = parse_us_number(value)
    marker = f"({value})"
    return -number if marker in context else number


def fetch_market_snapshot():
    snapshot = []
    for label, symbol in MARKET_SYMBOLS:
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{urllib.parse.quote(symbol)}?range=1d&interval=5m"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
            meta = payload["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            previous = meta.get("previousClose")
            day_low = meta.get("regularMarketDayLow")
            day_high = meta.get("regularMarketDayHigh")
            market_time = meta.get("regularMarketTime")
            change = price - previous if price is not None and previous else None
            change_pct = (change / previous * 100) if change is not None and previous else None
            when = (
                dt.datetime.fromtimestamp(market_time, dt.timezone.utc).astimezone(TIMEZONE)
                if market_time
                else None
            )
            state = meta.get("marketState", "")
        except Exception as exc:
            price = change = change_pct = day_low = day_high = when = None
            state = f"indisponivel: {type(exc).__name__}"

        snapshot.append(
            {
                "label": label,
                "symbol": symbol,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "day_low": day_low,
                "day_high": day_high,
                "time": when,
                "state": state,
            }
        )
    return snapshot


def fetch_weather_forecast():
    chart_locations = []
    summary_locations = []
    errors = []
    for spec in FORECAST_CHART_LOCATIONS:
        forecast = fetch_weather_location_forecast(spec, include_hourly=True, include_days=True)
        if forecast.get("available"):
            chart_locations.append(forecast)
        else:
            errors.append(f"{spec['label']}: {forecast.get('error', 'indisponivel')}")
    for spec in FORECAST_SUMMARY_LOCATIONS:
        forecast = fetch_weather_location_forecast(spec, include_hourly=False, include_days=False)
        if forecast.get("available"):
            summary_locations.append(forecast)
        else:
            errors.append(f"{spec['label']}: {forecast.get('error', 'indisponivel')}")
    if not chart_locations and not summary_locations:
        return {"available": False, "error": "; ".join(errors) or "forecast indisponivel"}
    return {
        "available": True,
        "chart_locations": chart_locations,
        "summary_locations": summary_locations,
        "errors": errors,
    }


def fetch_weather_location_forecast(location, include_hourly=True, include_days=True):
    if not location.get("lat") or not location.get("lon"):
        return {"available": False, "error": "coordenadas indisponiveis"}
    params_dict = {
        "latitude": location["lat"],
        "longitude": location["lon"],
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,precipitation",
        "timezone": "auto",
        "forecast_days": 3 if include_days else 1,
    }
    if include_hourly:
        params_dict["hourly"] = "temperature_2m,precipitation_probability"
    if include_days:
        params_dict["daily"] = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    params = urllib.parse.urlencode(
        params_dict
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "ChiefOfStaffDigital/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"available": False, "error": f"forecast indisponivel: {type(exc).__name__}"}

    current = payload.get("current", {}) or {}
    hourly = payload.get("hourly", {}) or {}
    daily = payload.get("daily", {}) or {}
    hourly_points = build_hourly_forecast_points(hourly, hours=12) if include_hourly else []
    days = []
    if include_days:
        for idx, date_value in enumerate(daily.get("time", [])[:3]):
            days.append(
                {
                    "date": date_value,
                    "code": daily_value(daily, "weather_code", idx),
                    "high_c": daily_value(daily, "temperature_2m_max", idx),
                    "low_c": daily_value(daily, "temperature_2m_min", idx),
                    "rain_pct": daily_value(daily, "precipitation_probability_max", idx),
                }
            )
    return {
        "available": True,
        "label": location.get("label", location.get("city", "Local")),
        "location": {
            "city": location.get("city", ""),
            "region": location.get("region", ""),
            "country": location.get("country", ""),
            "lat": location.get("lat"),
            "lon": location.get("lon"),
        },
        "temperature_c": current.get("temperature_2m"),
        "feels_c": current.get("apparent_temperature"),
        "weather_code": current.get("weather_code"),
        "wind_kmh": current.get("wind_speed_10m"),
        "wind_direction_deg": current.get("wind_direction_10m"),
        "precipitation_mm": current.get("precipitation"),
        "hourly": hourly_points,
        "days": days,
    }


def fetch_current_location():
    sources = [
        "https://ipapi.co/json/",
        "http://ip-api.com/json/?fields=status,message,city,regionName,country,lat,lon,timezone,countryCode",
    ]
    for url in sources:
        req = urllib.request.Request(url, headers={"User-Agent": "ChiefOfStaffDigital/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            continue
        lat = payload.get("latitude", payload.get("lat"))
        lon = payload.get("longitude", payload.get("lon"))
        if lat is None or lon is None:
            continue
        city = payload.get("city") or ""
        region = payload.get("region") or payload.get("regionName") or ""
        country = payload.get("country_name") or payload.get("country") or payload.get("countryCode") or ""
        return {
            "city": city,
            "region": region,
            "country": country,
            "lat": float(lat),
            "lon": float(lon),
        }
    return {"error": "nao foi possivel detectar a localizacao por IP"}


def daily_value(daily, key, idx):
    values = daily.get(key) or []
    return values[idx] if idx < len(values) else None


def build_hourly_forecast_points(hourly, hours=12):
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    rain_probs = hourly.get("precipitation_probability") or []
    now = dt.datetime.now(TIMEZONE).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    points = []
    for idx, value in enumerate(times):
        try:
            stamp = dt.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            continue
        if stamp < now:
            continue
        points.append(
            {
                "time": stamp,
                "temperature_c": hourly_value(temps, idx),
                "rain_pct": hourly_value(rain_probs, idx),
            }
        )
        if len(points) >= hours:
            break
    if points:
        return points

    for idx, value in enumerate(times[:hours]):
        try:
            stamp = dt.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            continue
        points.append(
            {
                "time": stamp,
                "temperature_c": hourly_value(temps, idx),
                "rain_pct": hourly_value(rain_probs, idx),
            }
        )
    return points


def hourly_value(values, idx):
    return values[idx] if idx < len(values) else None


def fetch_news_snapshot(limit_per_source=5):
    groups = []
    now = dt.datetime.now(TIMEZONE)
    for source, urls in NEWS_SOURCES:
        items = []
        errors = []
        for url in urls:
            try:
                items.extend(fetch_news_feed_items(source, url, 20))
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        items = filter_news_items_for_source(source, items)
        ranked = rank_news_items(items, source, now)
        selected = ranked[:limit_per_source]
        groups.append(
            {
                "source": source,
                "items": selected,
                "error": "" if selected else "; ".join(errors[:2]) or "feed indisponivel",
            }
        )
    return groups


def fetch_pluggy_snapshot():
    client_id = os.getenv("PLUGGY_CLIENT_ID", "").strip()
    client_secret = os.getenv("PLUGGY_CLIENT_SECRET", "").strip()
    item_ids = parse_env_list(os.getenv("PLUGGY_ITEM_IDS", ""))
    base_url = os.getenv("PLUGGY_BASE_URL", "https://api.pluggy.ai").rstrip("/")
    days = int(os.getenv("PLUGGY_TRANSACTIONS_DAYS", "7") or "7")
    if not client_id or not client_secret:
        return {
            "available": False,
            "configured": False,
            "error": "PLUGGY_CLIENT_ID/PLUGGY_CLIENT_SECRET nao configurados",
        }
    if not item_ids:
        return {
            "available": False,
            "configured": False,
            "error": "PLUGGY_ITEM_IDS nao configurado",
        }

    errors = []
    try:
        api_key = pluggy_api_key(base_url, client_id, client_secret)
    except Exception as exc:
        return {
            "available": False,
            "configured": True,
            "error": f"auth Pluggy: {type(exc).__name__}: {exc}",
        }

    items = []
    accounts = []
    transactions = []
    investments = []
    categories = []
    try:
        categories = pluggy_get_all(base_url, api_key, "/categories", {})
    except Exception as exc:
        errors.append(f"categories: {type(exc).__name__}: {exc}")
    for item_id in item_ids:
        item_accounts = []
        try:
            item = pluggy_get(base_url, api_key, f"/items/{urllib.parse.quote(item_id)}")
            items.append(item)
        except Exception as exc:
            errors.append(f"item {item_id}: {type(exc).__name__}: {exc}")
            item = {"id": item_id}
        try:
            item_accounts = pluggy_get_all(base_url, api_key, "/accounts", {"itemId": item_id})
            institution_name = pluggy_detect_institution(item, item_accounts)
            for account in item_accounts:
                account["itemId"] = item_id
                account["_institution"] = institution_name
            accounts.extend(item_accounts)
        except Exception as exc:
            errors.append(f"accounts {item_id}: {type(exc).__name__}: {exc}")
        try:
            item_investments = pluggy_get_all(base_url, api_key, "/investments", {"itemId": item_id})
            for investment in item_investments:
                investment["itemId"] = item_id
                investment["_institution"] = pluggy_detect_institution(item, item_accounts)
            investments.extend(item_investments)
        except Exception as exc:
            errors.append(f"investments {item_id}: {type(exc).__name__}: {exc}")

    today = dt.datetime.now(TIMEZONE).date()
    from_date = (today - dt.timedelta(days=max(days, 30))).isoformat()
    to_date = (today + dt.timedelta(days=90)).isoformat()
    for account in accounts[:25]:
        account_id = account.get("id")
        if not account_id:
            continue
        try:
            rows = pluggy_get_all_cursor(
                base_url,
                api_key,
                "/v2/transactions",
                {"accountId": str(account_id), "dateFrom": from_date, "dateTo": to_date},
            )
            for row in rows:
                row["_account"] = pluggy_account_label(account)
                row["_institution"] = account.get("_institution") or "-"
                row["_account_type"] = account.get("type") or ""
                row["_account_subtype"] = account.get("subtype") or ""
            transactions.extend(rows)
        except Exception as exc:
            errors.append(f"transactions {account_id}: {type(exc).__name__}: {exc}")

    return build_pluggy_summary(items, accounts, transactions, investments, categories, errors, days)


def parse_env_list(value):
    return [item.strip() for item in re.split(r"[,;\s]+", value or "") if item.strip()]


def pluggy_api_key(base_url, client_id, client_secret):
    payload = json.dumps({"clientId": client_id, "clientSecret": client_secret}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/auth",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ChiefOfStaffDigital/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    api_key = data.get("apiKey")
    if not api_key:
        raise RuntimeError("apiKey ausente na resposta Pluggy")
    return api_key


def pluggy_get(base_url, api_key, path, params=None):
    query = urllib.parse.urlencode(params or {})
    url = f"{base_url}{path}" + (f"?{query}" if query else "")
    req = urllib.request.Request(
        url,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/json",
            "User-Agent": "ChiefOfStaffDigital/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=18) as response:
        return json.loads(response.read().decode("utf-8"))


def pluggy_get_all(base_url, api_key, path, params=None, limit=200):
    params = dict(params or {})
    params.setdefault("pageSize", limit)
    rows = []
    page = 1
    while page <= 5:
        params["page"] = page
        payload = pluggy_get(base_url, api_key, path, params)
        page_rows = pluggy_payload_results(payload)
        rows.extend(page_rows)
        total_pages = payload.get("totalPages") or payload.get("total_pages")
        if total_pages and page >= int(total_pages):
            break
        if not page_rows or len(page_rows) < int(params.get("pageSize") or limit):
            break
        page += 1
    return rows


def pluggy_get_all_cursor(base_url, api_key, path, params=None, max_pages=5):
    """Collect Pluggy v2 cursor pages without falling back to page numbers."""
    request_path = path
    request_params = dict(params or {})
    rows = []
    for _ in range(max_pages):
        payload = pluggy_get(base_url, api_key, request_path, request_params)
        rows.extend(pluggy_payload_results(payload))
        next_link = payload.get("next") if isinstance(payload, dict) else None
        if not next_link:
            break
        parsed = urllib.parse.urlparse(next_link)
        request_path = parsed.path or path
        request_params = {
            key: values[-1]
            for key, values in urllib.parse.parse_qs(parsed.query).items()
            if values
        }
    return rows


def pluggy_payload_results(payload):
    if isinstance(payload, list):
        return payload
    for key in ("results", "data", "items", "accounts", "transactions", "investments"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, list):
            return value
    return []


def pluggy_item_institution_name(item):
    connector = (item or {}).get("connector") or {}
    institution = (item or {}).get("institution") or {}
    return (
        connector.get("name")
        or institution.get("name")
        or (item or {}).get("name")
        or (item or {}).get("institutionName")
        or "-"
    )


def pluggy_detect_institution(item, accounts=None):
    raw_names = [pluggy_item_institution_name(item)]
    raw_names.extend((account or {}).get("name") or "" for account in (accounts or []))
    haystack = normalize_ws(" ".join(raw_names)).lower()
    if "santander" in haystack or "aadvantage" in haystack:
        return "Santander"
    if "itau" in haystack or "itaú" in haystack or "personnalite" in haystack or "azul itau" in haystack:
        return "Itau"
    if "btg" in haystack:
        return "BTG Pactual"
    return pluggy_item_institution_name(item)


def build_pluggy_summary(items, accounts, transactions, investments, categories, errors, days):
    account_rows = [pluggy_account_summary(account) for account in accounts]
    account_rows = sorted(account_rows, key=lambda row: (row.get("institution") or "", row.get("name") or ""))
    bank_accounts = [row for row in account_rows if row.get("product") == "BANK"]
    credit_cards = [row for row in account_rows if row.get("product") == "CREDIT"]
    total_brl = sum(row.get("balance") or 0 for row in bank_accounts if row.get("currency") == "BRL")
    total_card_balance_brl = sum(row.get("balance") or 0 for row in credit_cards if row.get("currency") == "BRL")
    investment_rows = [pluggy_investment_summary(row) for row in investments]
    investment_rows = [
        row
        for row in investment_rows
        if row.get("status") in {"ACTIVE", "PENDING"}
        or (not row.get("status") and (row.get("value") or 0) > 0)
    ]
    total_investments_brl = sum(row.get("value") or 0 for row in investment_rows if row.get("currency") == "BRL")
    tx_rows = [pluggy_transaction_summary(row) for row in transactions]
    cash_rows = [row for row in tx_rows if row.get("account_type") == "BANK" and pluggy_date_within_days(row.get("date"), days)]
    debit_total = sum(abs(row["amount"]) for row in cash_rows if row.get("amount", 0) < 0)
    credit_total = sum(row["amount"] for row in cash_rows if row.get("amount", 0) > 0)
    category_lookup = pluggy_category_lookup(categories)
    expense_categories = pluggy_expense_category_summary(tx_rows, category_lookup)
    past_expenses = sum(row.get("past") or 0 for row in expense_categories)
    future_expenses = sum(row.get("future") or 0 for row in expense_categories)
    tx_rows = sorted(tx_rows, key=lambda row: (row.get("date") or "", abs(row.get("amount") or 0)), reverse=True)
    return {
        "available": bool(account_rows or investment_rows or tx_rows),
        "configured": True,
        "items_count": len(items),
        "accounts": account_rows,
        "bank_accounts": bank_accounts,
        "credit_cards": credit_cards,
        "investments": investment_rows,
        "transactions": tx_rows,
        "total_brl": total_brl,
        "total_card_balance_brl": total_card_balance_brl,
        "total_investments_brl": total_investments_brl,
        "debit_total": debit_total,
        "credit_total": credit_total,
        "expense_categories": expense_categories,
        "past_expenses": past_expenses,
        "future_expenses": future_expenses,
        "days": days,
        "errors": errors,
        "source": "Pluggy Open Finance",
        "error": "; ".join(errors) or "sem dados retornados",
    }


def pluggy_account_summary(account):
    raw_balance = None
    for key in ("balance", "currentBalance", "availableBalance", "amount"):
        if account.get(key) is not None:
            raw_balance = account.get(key)
            break
    balance = pluggy_amount(raw_balance)
    currency = account.get("currencyCode") or account.get("currency") or "BRL"
    owner = account.get("owner") or {}
    credit_data = account.get("creditData") or {}
    product = str(account.get("type") or "").upper()
    return {
        "id": account.get("id"),
        "institution": account.get("_institution") or "-",
        "name": account.get("name") or account.get("marketingName") or account.get("number") or "Conta",
        "type": account.get("type") or account.get("subtype") or "-",
        "subtype": account.get("subtype") or "-",
        "product": product,
        "number": mask_account_number(account.get("number") or account.get("displayNumber") or ""),
        "balance": balance,
        "currency": currency,
        "owner": owner.get("name") if isinstance(owner, dict) else "",
        "available_credit": pluggy_amount(credit_data.get("availableCreditLimit")),
        "credit_limit": pluggy_amount(credit_data.get("creditLimit")),
        "due_date": normalize_ws(str(credit_data.get("balanceDueDate") or ""))[:10],
    }


def pluggy_investment_summary(investment):
    # Pluggy's `amount` is the gross market position (quantity x unit value).
    # `balance` is the estimated net redemption value and must not replace it.
    gross_value = pluggy_amount(investment.get("amount"))
    unit_value = pluggy_amount(investment.get("value"))
    quantity = pluggy_amount(investment.get("quantity"))
    calculated_value = None
    if unit_value is not None and quantity is not None:
        calculated_value = unit_value * quantity
    if gross_value in (None, 0) and calculated_value not in (None, 0):
        gross_value = calculated_value
    if gross_value is None:
        gross_value = pluggy_amount(investment.get("grossAmount"))
    net_value = pluggy_amount(investment.get("balance"))
    if net_value is None:
        net_value = pluggy_amount(investment.get("netAmount"))
    if gross_value is None:
        gross_value = net_value
    currency = investment.get("currencyCode") or investment.get("currency") or "BRL"
    return {
        "id": investment.get("id"),
        "item_id": investment.get("itemId"),
        "institution": investment.get("_institution") or "-",
        "name": investment.get("name") or investment.get("code") or investment.get("type") or "Investimento",
        "type": investment.get("type") or investment.get("subtype") or "-",
        "value": gross_value,
        "net_value": net_value,
        "unit_value": unit_value,
        "quantity": quantity,
        "currency": currency,
        "status": str(investment.get("status") or "").upper(),
        "as_of": normalize_ws(str(investment.get("date") or investment.get("updatedAt") or ""))[:10],
    }


def pluggy_transaction_summary(transaction):
    amount = pluggy_amount(transaction.get("amount") or transaction.get("value"))
    credit_metadata = transaction.get("creditCardMetadata") or {}
    return {
        "date": normalize_ws(str(transaction.get("date") or transaction.get("postedDate") or ""))[:10],
        "description": normalize_ws(transaction.get("description") or transaction.get("merchantName") or transaction.get("category") or "Transacao"),
        "amount": amount or 0,
        "currency": transaction.get("currencyCode") or transaction.get("currency") or "BRL",
        "account": transaction.get("_account") or "-",
        "institution": transaction.get("_institution") or "-",
        "account_type": str(transaction.get("_account_type") or "").upper(),
        "account_subtype": str(transaction.get("_account_subtype") or "").upper(),
        "status": str(transaction.get("status") or "").upper(),
        "category": transaction.get("category") or "Outros",
        "category_id": str(transaction.get("categoryId") or ""),
        "bill_forecast_date": str(credit_metadata.get("billForecastDate") or "")[:7],
    }


def pluggy_date_within_days(value, days):
    try:
        row_date = dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return False
    today = dt.datetime.now(TIMEZONE).date()
    return today - dt.timedelta(days=max(1, int(days))) <= row_date <= today


def pluggy_category_lookup(categories):
    lookup = {}
    for category in categories or []:
        category_id = str(category.get("id") or "")
        if not category_id:
            continue
        lookup[category_id] = (
            category.get("descriptionTranslated")
            or category.get("description")
            or "Outros"
        )
    return lookup


def pluggy_expense_category_summary(transactions, category_lookup):
    today = dt.datetime.now(TIMEZONE).date()
    start_date = today - dt.timedelta(days=30)
    current_month = today.strftime("%Y-%m")
    totals = {}
    for row in transactions or []:
        amount = pluggy_amount(row.get("amount")) or 0
        category_id = str(row.get("category_id") or "")
        category_name = str(row.get("category") or "Outros")
        category_lower = category_name.lower()
        if category_id.startswith("04") or "same person transfer" in category_lower:
            continue
        if category_id == "05100000" or "credit card payment" in category_lower:
            continue

        is_credit_card = row.get("account_type") == "CREDIT"
        expense = amount if is_credit_card and amount > 0 else abs(amount) if not is_credit_card and amount < 0 else 0
        if expense <= 0:
            continue
        try:
            row_date = dt.date.fromisoformat(str(row.get("date") or "")[:10])
        except ValueError:
            continue

        is_future = (
            row_date > today
            or row.get("status") == "PENDING"
            or bool(row.get("bill_forecast_date") and row.get("bill_forecast_date") > current_month)
        )
        is_past = not is_future and start_date <= row_date <= today
        if not is_future and not is_past:
            continue

        root_id = f"{category_id[:2]}000000" if len(category_id) >= 2 else ""
        label = category_lookup.get(root_id) or category_lookup.get(category_id) or category_name or "Outros"
        item = totals.setdefault(label, {"category": label, "past": 0.0, "future": 0.0})
        item["future" if is_future else "past"] += expense

    rows = sorted(totals.values(), key=lambda item: (item["past"] + item["future"]), reverse=True)
    if len(rows) <= 7:
        return rows
    visible = rows[:7]
    remainder = rows[7:]
    visible.append(
        {
            "category": "Outras",
            "past": sum(item["past"] for item in remainder),
            "future": sum(item["future"] for item in remainder),
        }
    )
    return visible


def pluggy_amount(value):
    if isinstance(value, dict):
        for key in ("amount", "value", "current", "balance"):
            if key in value:
                return pluggy_amount(value.get(key))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pluggy_account_label(account):
    institution = account.get("_institution") or "-"
    name = account.get("name") or account.get("marketingName") or account.get("type") or "Conta"
    return f"{institution} - {name}"


def mask_account_number(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return ""
    return "*" * max(0, len(digits) - 4) + digits[-4:]


def fetch_world_cup_snapshot(day):
    yesterday = day - dt.timedelta(days=1)
    rows = []
    errors = []
    used_dynamic = False
    top_scorers = []
    scorer_source = "ESPN"

    for target_date, period in ((yesterday, "Yesterday"), (day, "Today")):
        dynamic_rows = []
        try:
            dynamic_rows = fetch_espn_world_cup_rows(target_date, period)
        except Exception as exc:
            errors.append(f"{period}: {type(exc).__name__}: {exc}")
        if dynamic_rows:
            rows.extend(dynamic_rows)
            used_dynamic = True
        else:
            rows.extend(static_world_cup_rows_for_date(target_date, period))

    try:
        top_scorers = fetch_espn_world_cup_top_scorers(limit=5)
    except Exception as exc:
        errors.append(f"Top scorers: {type(exc).__name__}: {exc}")
        top_scorers = [dict(item) for item in WORLD_CUP_STATIC_TOP_SCORERS]
        scorer_source = "static fallback"
    if not top_scorers:
        top_scorers = [dict(item) for item in WORLD_CUP_STATIC_TOP_SCORERS]
        scorer_source = "static fallback"

    rows.sort(key=world_cup_sort_key)
    if rows:
        match_errors = [error for error in errors if not error.startswith("Top scorers:")]
        if used_dynamic and match_errors:
            source = "ESPN + FIFA schedule fallback"
        elif used_dynamic:
            source = "ESPN"
        elif any("Guardian" in row.get("source", "") for row in rows):
            source = "Guardian/FIFA schedule fallback"
        else:
            source = "FIFA schedule fallback"
        return {
            "available": True,
            "rows": rows,
            "top_scorers": top_scorers,
            "source": source,
            "scorer_source": scorer_source,
            "errors": errors,
        }
    return {
        "available": False,
        "rows": [],
        "top_scorers": top_scorers,
        "source": "",
        "scorer_source": scorer_source,
        "errors": errors,
        "error": "; ".join(errors) or "sem jogos encontrados",
    }


def fetch_brasileirao_snapshot(day):
    errors = []
    standings = []
    current_matches = []
    next_matches = []
    top_scorers = []

    try:
        standings = fetch_espn_brasileirao_standings()
    except Exception as exc:
        errors.append(f"Classificacao: {type(exc).__name__}: {exc}")

    try:
        matches = fetch_espn_brasileirao_match_window(day)
        current_matches, next_matches = split_brasileirao_rounds(matches, day)
    except Exception as exc:
        errors.append(f"Jogos: {type(exc).__name__}: {exc}")

    try:
        top_scorers = fetch_espn_brasileirao_top_scorers(limit=5)
    except Exception as exc:
        errors.append(f"Artilheiros: {type(exc).__name__}: {exc}")

    available = bool(standings or current_matches or next_matches or top_scorers)
    return {
        "available": available,
        "standings": standings,
        "current_matches": current_matches,
        "next_matches": next_matches,
        "top_scorers": top_scorers,
        "source": "ESPN",
        "errors": errors,
        "error": "; ".join(errors) or "dados indisponiveis",
    }


def fetch_espn_brasileirao_standings():
    url = (
        "https://site.web.api.espn.com/apis/v2/sports/soccer/bra.1/standings?"
        "region=br&lang=pt&contentorigin=espn"
    )
    payload = fetch_json_url(url, timeout=12)
    standings = (((payload.get("children") or [{}])[0]).get("standings") or {})
    rows = []
    for idx, entry in enumerate(standings.get("entries") or [], 1):
        team = entry.get("team") or {}
        stats = {stat.get("name"): stat for stat in entry.get("stats") or []}
        rows.append(
            {
                "rank": idx,
                "team": team.get("displayName") or team.get("shortDisplayName") or team.get("name") or "-",
                "abbrev": team.get("abbreviation") or "",
                "logo": espn_team_logo_from_team(team),
                "played": stat_display(stats, "gamesPlayed"),
                "wins": stat_display(stats, "wins"),
                "ties": stat_display(stats, "ties"),
                "losses": stat_display(stats, "losses"),
                "goal_diff": stat_display(stats, "pointDifferential"),
                "points": stat_display(stats, "points"),
            }
        )
    return rows


def stat_display(stats, name):
    value = (stats.get(name) or {}).get("displayValue")
    if value is not None:
        return str(value)
    raw = (stats.get(name) or {}).get("value")
    if raw is None:
        return "-"
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return str(raw)


def fetch_espn_brasileirao_match_window(day):
    matches = []
    seen = set()
    for offset in range(-3, 22):
        target = day + dt.timedelta(days=offset)
        try:
            rows = fetch_espn_brasileirao_rows(target)
        except Exception:
            continue
        for row in rows:
            key = row.get("id") or f"{row.get('date')}|{row.get('match')}"
            if key in seen:
                continue
            seen.add(key)
            matches.append(row)
    matches.sort(key=brasileirao_match_sort_key)
    return matches


def fetch_espn_brasileirao_rows(target_date):
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/soccer/bra.1/scoreboard?"
        f"dates={target_date.strftime('%Y%m%d')}"
    )
    payload = fetch_json_url(url, timeout=12)
    rows = []
    for event in payload.get("events") or []:
        row = parse_espn_brasileirao_event(event, target_date)
        if row:
            rows.append(row)
    return rows


def parse_espn_brasileirao_event(event, target_date):
    competition = first_or_empty(event.get("competitions"))
    competitors = competition.get("competitors") or []
    if len(competitors) < 2:
        return None
    home = next((item for item in competitors if item.get("homeAway") == "home"), competitors[0])
    away = next((item for item in competitors if item.get("homeAway") == "away"), competitors[1])
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    kickoff = parse_espn_datetime(event.get("date") or competition.get("date"))
    venue = competition.get("venue") or event.get("venue") or {}
    home_name = espn_team_name(home)
    away_name = espn_team_name(away)
    score = world_cup_score_text(home, away, status_type)
    time_text = format_brasileirao_time(kickoff)
    return {
        "id": event.get("id") or competition.get("id"),
        "date": target_date,
        "kickoff": kickoff,
        "home_team": home_name,
        "away_team": away_name,
        "home_flag": espn_team_logo(home),
        "away_flag": espn_team_logo(away),
        "match": f"{home_name} vs {away_name}",
        "detail": score if score else time_text,
        "time": time_text,
        "status": brasileirao_status_label(status_type),
        "stadium": espn_venue_name(venue),
        "region": espn_venue_region(venue),
    }


def split_brasileirao_rounds(matches, day):
    if not matches:
        return [], []
    today_start = dt.datetime.combine(day, dt.time.min).replace(tzinfo=TIMEZONE)
    current_start = today_start - dt.timedelta(days=2)
    current_end = today_start + dt.timedelta(days=3, hours=23, minutes=59)
    current = [
        match for match in matches
        if match.get("kickoff") and current_start <= match["kickoff"].astimezone(TIMEZONE) <= current_end
    ]
    if not current:
        future_or_recent = [
            match for match in matches
            if not match.get("kickoff") or match["kickoff"].astimezone(TIMEZONE) >= current_start
        ]
        current = future_or_recent[:10]

    current_ids = {match.get("id") for match in current if match.get("id")}
    latest_current = max(
        (match["kickoff"].astimezone(TIMEZONE) for match in current if match.get("kickoff")),
        default=current_end,
    )
    next_round = [
        match for match in matches
        if match.get("id") not in current_ids
        and match.get("kickoff")
        and match["kickoff"].astimezone(TIMEZONE) > latest_current
    ][:10]
    return current[:10], next_round


def fetch_espn_brasileirao_top_scorers(limit=5):
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/bra.1/statistics"
    payload = fetch_json_url(url, timeout=12)
    goals_group = next(
        (group for group in payload.get("stats") or [] if group.get("name") == "goalsLeaders"),
        {},
    )
    scorers = []
    for idx, item in enumerate((goals_group.get("leaders") or [])[:limit], 1):
        athlete = item.get("athlete") or {}
        team = athlete.get("team") or item.get("team") or {}
        scorers.append(
            {
                "rank": idx,
                "player": athlete.get("displayName") or athlete.get("shortName") or "-",
                "team": team.get("displayName") or team.get("name") or team.get("abbreviation") or "-",
                "team_flag": espn_team_logo_from_team(team),
                "goals": int(float(item.get("value") or 0)),
                "matches": parse_world_cup_matches_from_display(item.get("displayValue")),
            }
        )
    return scorers


def brasileirao_status_label(status_type):
    state = (status_type.get("state") or "").lower()
    completed = bool(status_type.get("completed"))
    detail = normalize_ws(status_type.get("shortDetail") or status_type.get("detail") or "")
    if state == "in":
        return detail or "Ao vivo"
    if completed or state == "post":
        return "FT"
    return "Fixture"


def format_brasileirao_time(kickoff):
    if not kickoff:
        return "A confirmar"
    return kickoff.astimezone(TIMEZONE).strftime("%d/%m %H:%M")


def brasileirao_match_sort_key(row):
    kickoff = row.get("kickoff")
    kickoff_order = kickoff.timestamp() if hasattr(kickoff, "timestamp") else 9999999999
    return (kickoff_order, row.get("match", ""))


def fetch_json_url(url, timeout=10):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ChiefOfStaffDigital/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_espn_world_cup_top_scorers(limit=5):
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/statistics"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ChiefOfStaffDigital/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    goals_group = next(
        (group for group in payload.get("stats") or [] if group.get("name") == "goalsLeaders"),
        {},
    )
    scorers = []
    for idx, item in enumerate((goals_group.get("leaders") or [])[:limit], 1):
        athlete = item.get("athlete") or {}
        team = athlete.get("team") or item.get("team") or {}
        scorers.append(
            {
                "rank": idx,
                "player": athlete.get("displayName") or athlete.get("shortName") or "-",
                "team": team.get("displayName") or team.get("name") or team.get("abbreviation") or "-",
                "team_flag": espn_team_logo_from_team(team),
                "goals": int(float(item.get("value") or 0)),
                "matches": parse_world_cup_matches_from_display(item.get("displayValue")),
            }
        )
    return scorers


def parse_world_cup_matches_from_display(value):
    match = re.search(r"Matches:\s*(\d+)", value or "", re.I)
    return int(match.group(1)) if match else None


def fetch_espn_world_cup_rows(target_date, period):
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?"
        f"dates={target_date.strftime('%Y%m%d')}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ChiefOfStaffDigital/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    rows = []
    for event in payload.get("events") or []:
        competition = first_or_empty(event.get("competitions"))
        competitors = competition.get("competitors") or []
        if len(competitors) < 2:
            continue
        home = next((item for item in competitors if item.get("homeAway") == "home"), competitors[0])
        away = next((item for item in competitors if item.get("homeAway") == "away"), competitors[1])
        status = competition.get("status") or event.get("status") or {}
        status_type = status.get("type") or {}
        kickoff = parse_espn_datetime(event.get("date") or competition.get("date"))
        venue = competition.get("venue") or event.get("venue") or {}
        score = world_cup_score_text(home, away, status_type)
        time_text = format_world_cup_time(kickoff)
        home_name = espn_team_name(home)
        away_name = espn_team_name(away)
        rows.append(
            {
                "period": period,
                "date": target_date,
                "group": world_cup_group_from_event(event),
                "home_team": home_name,
                "away_team": away_name,
                "match": f"{home_name} vs {away_name}",
                "home_flag": espn_team_logo(home) or WORLD_CUP_FLAG_URLS.get(home_name, ""),
                "away_flag": espn_team_logo(away) or WORLD_CUP_FLAG_URLS.get(away_name, ""),
                "detail": score if score else time_text,
                "time": time_text,
                "status": world_cup_status_label(status_type, period),
                "region": espn_venue_region(venue),
                "stadium": espn_venue_name(venue),
                "kickoff": kickoff,
                "source": "ESPN",
            }
        )
    return rows


def first_or_empty(items):
    return items[0] if items else {}


def parse_espn_datetime(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(TIMEZONE)
    except ValueError:
        return None


def espn_team_name(competitor):
    team = competitor.get("team") or {}
    return (
        team.get("shortDisplayName")
        or team.get("displayName")
        or team.get("name")
        or competitor.get("displayName")
        or "-"
    )


def espn_team_logo(competitor):
    team = competitor.get("team") or {}
    return normalize_ws(team.get("logo", ""))


def espn_team_logo_from_team(team):
    logo = normalize_ws((team or {}).get("logo", ""))
    if logo:
        return logo
    logos = (team or {}).get("logos") or []
    for item in logos:
        href = normalize_ws(item.get("href", ""))
        if href:
            return href
    return WORLD_CUP_FLAG_URLS.get((team or {}).get("displayName") or (team or {}).get("name") or "", "")


def world_cup_score_text(home, away, status_type):
    state = (status_type.get("state") or "").lower()
    completed = bool(status_type.get("completed"))
    if state not in {"post", "in"} and not completed:
        return ""
    home_score = normalize_ws(str(home.get("score", "")))
    away_score = normalize_ws(str(away.get("score", "")))
    if home_score == "" or away_score == "":
        return ""
    if state == "in":
        return f"{home_score}-{away_score} ao vivo"
    return f"{home_score}-{away_score}"


def world_cup_status_label(status_type, period):
    state = (status_type.get("state") or "").lower()
    completed = bool(status_type.get("completed"))
    if state == "in":
        return "Live"
    if completed or state == "post":
        return "Result"
    if period == "Yesterday":
        return "Result pending"
    return "Fixture"


def world_cup_group_from_event(event):
    name = normalize_ws(event.get("name", ""))
    match = re.search(r"\bGroup\s+([A-Z])\b", name, re.I)
    return match.group(1).upper() if match else "-"


def espn_venue_name(venue):
    return normalize_ws(venue.get("fullName") or venue.get("name") or "-")


def espn_venue_region(venue):
    address = venue.get("address") or {}
    return normalize_ws(
        address.get("state")
        or address.get("region")
        or address.get("city")
        or venue.get("city")
        or "-"
    )


def static_world_cup_rows_for_date(target_date, period):
    rows = []
    target = target_date.isoformat()
    for order, match in enumerate(WORLD_CUP_STATIC_MATCHES):
        if match.get("date") != target:
            continue
        score = match.get("score", "")
        is_yesterday = period == "Yesterday"
        kickoff = parse_espn_datetime(match.get("kickoff_utc"))
        rows.append(
            {
                "period": period,
                "date": target_date,
                "group": match.get("group", "-"),
                "home_team": match.get("home", "-"),
                "away_team": match.get("away", "-"),
                "match": f"{match.get('home', '-')} vs {match.get('away', '-')}",
                "home_flag": WORLD_CUP_FLAG_URLS.get(match.get("home", ""), ""),
                "away_flag": WORLD_CUP_FLAG_URLS.get(match.get("away", ""), ""),
                "detail": score or ("Resultado a confirmar" if is_yesterday else format_world_cup_time(kickoff)),
                "time": format_world_cup_time(kickoff),
                "status": "Result" if score else ("Result pending" if is_yesterday else "Fixture"),
                "region": match.get("region", "-"),
                "stadium": match.get("stadium", "-"),
                "kickoff": kickoff,
                "order": order,
                "source": "Guardian/FIFA schedule fallback" if kickoff else "FIFA schedule fallback",
            }
        )
    return rows


def format_world_cup_time(kickoff):
    if not kickoff:
        return "A confirmar"
    return kickoff.astimezone(TIMEZONE).strftime("%H:%M BRT")


def world_cup_sort_key(row):
    period_order = 0 if row.get("period") == "Yesterday" else 1
    kickoff = row.get("kickoff")
    kickoff_order = kickoff.timestamp() if hasattr(kickoff, "timestamp") else 9999999999
    return (period_order, kickoff_order, row.get("order", 9999), row.get("match", ""))


def filter_news_items_for_source(source, items):
    if source != "Globo.com":
        return items
    return [item for item in items if is_globo_allowed_news_item(item)]


def is_globo_allowed_news_item(item):
    feed_url = normalize_ws(item.get("feed_url", ""))
    link = normalize_ws(item.get("link", ""))
    title = normalize_news_text(item.get("title", ""))
    haystack = f"{feed_url} {link} {title}".lower()
    return any(term in haystack for term in GLOBO_ALLOWED_NEWS_TERMS)


def fetch_news_feed_items(source, url, limit):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        payload = response.read()
    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
    root = ET.fromstring(payload)
    items = parse_rss_items(root)
    if not items:
        items = parse_atom_items(root)
    clean_items = []
    seen = set()
    for item in items:
        title = best_news_title(item)
        if source == "Bloomberg":
            title = clean_bloomberg_news_title(title)
        link = normalize_ws(item.get("link", ""))
        key = normalize_news_key(link or title)
        if not title or key in seen:
            continue
        seen.add(key)
        published_raw = item.get("published", "")
        clean_items.append(
            {
                "source": source,
                "title": title,
                "link": link,
                "published": normalize_news_date(published_raw),
                "published_raw": published_raw,
                "published_dt": parse_news_datetime(published_raw),
                "feed_url": url,
            }
        )
        if len(clean_items) >= limit:
            break
    return clean_items


def rank_news_items(items, source, now):
    deduped = {}
    for item in items:
        key = normalize_news_key(item.get("link") or item.get("title"))
        if not key:
            continue
        score = score_news_item(item, source, now)
        current = deduped.get(key)
        if current is None or score > current[0]:
            deduped[key] = (score, item)
    ranked = sorted(
        deduped.values(),
        key=lambda pair: (
            pair[0],
            min(news_timestamp(pair[1].get("published_dt")), now.timestamp()),
        ),
        reverse=True,
    )
    clean_ranked = []
    for score, item in ranked:
        clean_item = dict(item)
        clean_item["published"] = format_news_display_date(
            clean_item.get("published_dt"),
            clean_item.get("published_raw", ""),
            now,
        )
        clean_item["news_score"] = score
        clean_ranked.append(clean_item)
    return clean_ranked


def score_news_item(item, source, now):
    title = normalize_news_text(item.get("title", ""))
    link = normalize_ws(item.get("link", ""))
    feed_url = normalize_ws(item.get("feed_url", ""))
    haystack = f"{title} {link} {feed_url}".lower()
    score = 0

    published = item.get("published_dt")
    if published and published.tzinfo is None:
        published = published.replace(tzinfo=TIMEZONE)
    if published:
        published = published.astimezone(TIMEZONE)
        future_minutes = (published - now).total_seconds() / 60
        if future_minutes > 10:
            score -= 70 + min(60, int(future_minutes // 15) * 8)
        age_hours = max(0.0, (now - published).total_seconds() / 3600)
        if future_minutes > 10:
            pass
        elif age_hours <= 6:
            score += 42
        elif age_hours <= 12:
            score += 34
        elif age_hours <= 24:
            score += 25
        elif age_hours <= 48:
            score += 12
        else:
            score -= min(35, int(age_hours // 12))
    else:
        score -= 18

    category_weights = {
        "macro": 18,
        "markets": 18,
        "business": 14,
        "geopolitics": 14,
    }
    for category, terms in NEWS_RELEVANCE_KEYWORDS.items():
        hits = sum(1 for term in terms if term in haystack)
        if hits:
            score += category_weights.get(category, 10) + min(18, (hits - 1) * 5)

    if any(term in feed_url for term in ("economia", "markets", "economics", "politica", "politics", "mundo", "world")):
        score += 16
    if source in {"Bloomberg", "CNBC"}:
        score += 8
    if source in {"Globo.com", "UOL"} and any(term in haystack for term in ("brasil", "lula", "stf", "congresso", "selic", "ipca", "dolar", "dólar")):
        score += 8

    noise_hits = sum(1 for term in NEWS_NOISE_KEYWORDS if term in haystack)
    if noise_hits:
        score -= 28 + (noise_hits - 1) * 8

    if len(title) < 35:
        score -= 6
    if not link:
        score -= 4
    return score


def news_timestamp(value):
    if not value:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=TIMEZONE)
    return value.timestamp()


def normalize_news_key(value):
    value = normalize_ws(value or "").lower()
    value = urllib.parse.urlsplit(value)._replace(query="", fragment="").geturl() if value.startswith(("http://", "https://")) else value
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return value.strip()


def best_news_title(item):
    title = normalize_news_text(item.get("title", ""))
    description = normalize_news_text(item.get("description", ""))
    generic_titles = {
        "frente a frente",
        "uol news",
        "uol",
        "noticias",
    }
    if description and (len(title) < 24 or title.lower() in generic_titles):
        return shorten_news_title(description)
    return shorten_news_title(title)


def clean_bloomberg_news_title(title):
    title = re.sub(r"\s+-\s+Bloomberg(?:\.com)?\s*$", "", normalize_ws(title), flags=re.I)
    return title


def shorten_news_title(value, limit=180):
    value = normalize_ws(value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip(" ,.;") + "..."


def parse_rss_items(root):
    parsed = []
    for node in root.findall(".//item"):
        link = find_xml_text(node, "link")
        parsed.append(
            {
                "title": find_xml_text(node, "title"),
                "description": find_xml_text(node, "description"),
                "link": link,
                "published": find_xml_text(node, "pubDate") or find_xml_text(node, "date"),
            }
        )
    return parsed


def parse_atom_items(root):
    parsed = []
    for node in root.findall(".//{http://www.w3.org/2005/Atom}entry") + root.findall(".//entry"):
        link = ""
        for link_node in list(node):
            if strip_xml_namespace(link_node.tag) != "link":
                continue
            link = link_node.attrib.get("href") or (link_node.text or "")
            if link:
                break
        parsed.append(
            {
                "title": find_xml_text(node, "title"),
                "description": find_xml_text(node, "summary") or find_xml_text(node, "content"),
                "link": link,
                "published": find_xml_text(node, "updated") or find_xml_text(node, "published"),
            }
        )
    return parsed


def find_xml_text(node, tag_name):
    for child in list(node):
        if strip_xml_namespace(child.tag) == tag_name:
            return child.text or ""
    return ""


def strip_xml_namespace(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def normalize_news_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return normalize_ws(value)


def normalize_news_date(value):
    value = normalize_news_text(value)
    if not value:
        return "-"
    parsed = parse_news_datetime(value)
    if parsed:
        if parsed.tzinfo:
            parsed = parsed.astimezone(TIMEZONE)
        return parsed.strftime("%d/%m %H:%M")
    return value[:24]


def format_news_display_date(parsed, raw_value="", now=None):
    now = now or dt.datetime.now(TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TIMEZONE)
    else:
        now = now.astimezone(TIMEZONE)
    if parsed is None:
        parsed = parse_news_datetime(raw_value)
    if parsed is None:
        return "-"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIMEZONE)
    parsed = parsed.astimezone(TIMEZONE)
    if parsed > now + dt.timedelta(minutes=10):
        return "Recente"
    return parsed.strftime("%d/%m %H:%M")


def parse_news_datetime(value):
    value = normalize_news_text(value)
    if not value:
        return None
    parsed = parsedate_to_datetime_safe(value)
    if parsed:
        if parsed.tzinfo is None and news_raw_date_looks_utc(value):
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    iso_value = value.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(iso_value)
    except ValueError:
        return None


def news_raw_date_looks_utc(value):
    value = normalize_ws(value or "").upper()
    return bool(re.search(r"(?:^|[\s,])(?:UT|UTC|GMT|Z|\+0000|-0000)(?:$|[\s,])", value))


def parsedate_to_datetime_safe(value):
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(value)
    except Exception:
        return None


def weather_code_label(code):
    labels = {
        0: "Ceu limpo",
        1: "Principalmente limpo",
        2: "Parcialmente nublado",
        3: "Nublado",
        45: "Nevoeiro",
        48: "Nevoeiro gelado",
        51: "Garoa leve",
        53: "Garoa",
        55: "Garoa forte",
        61: "Chuva leve",
        63: "Chuva",
        65: "Chuva forte",
        71: "Neve leve",
        73: "Neve",
        75: "Neve forte",
        80: "Pancadas leves",
        81: "Pancadas de chuva",
        82: "Pancadas fortes",
        95: "Trovoadas",
        96: "Trovoadas com granizo",
        99: "Trovoadas fortes",
    }
    return labels.get(code, "Tempo indisponivel")


def format_temp_c(value):
    if value is None:
        return "-"
    return f"{value:.0f}C"


def format_temp_c_chart(value):
    if value is None:
        return "-"
    return f"{value:.1f}C".replace(".", ",")


def format_temp_pair(value):
    if value is None:
        return "-"
    fahrenheit = (value * 9 / 5) + 32
    return f"{value:.0f}C / {fahrenheit:.0f}F"


def format_forecast_rain_mm(value):
    if value is None:
        return "-"
    return f"{value:.1f} mm"


def format_wind_direction(value):
    if value is None:
        return ""
    try:
        degrees = float(value) % 360
    except (TypeError, ValueError):
        return ""
    directions = ["N", "NE", "L", "SE", "S", "SO", "O", "NO"]
    idx = int((degrees + 22.5) // 45) % len(directions)
    return directions[idx]


def format_forecast_wind(value, direction=None):
    if value is None:
        return "-"
    wind_kts = float(value) * 0.539956803
    direction_label = format_wind_direction(direction)
    suffix = f" {direction_label}" if direction_label else ""
    return f"{wind_kts:.0f} kts{suffix}"


def build_candidate_screening_universe():
    universe = {group: [dict(item) for item in items] for group, items in CANDIDATE_UNIVERSE.items()}
    if not BROAD_CANDIDATE_SCREENING:
        return universe
    try:
        b3_items = build_b3_screen_items()
        universe["B3"] = merge_candidate_universe(
            b3_items[:BROAD_B3_PREFILTER_LIMIT] + universe.get("B3", [])
        )
    except Exception as exc:
        print(f"Broad B3 universe failed, using curated list: {type(exc).__name__}: {exc}", file=sys.stderr)
    try:
        listing_map = fetch_us_listing_map()
        stock_rows = fetch_stockanalysis_payload("https://stockanalysis.com/stocks/screener/")
        etf_rows = fetch_stockanalysis_payload("https://stockanalysis.com/etf/screener/")
        for group in ("Nasdaq", "NYSE"):
            stocks = build_us_stock_screen_items(group, stock_rows, listing_map)
            etfs = build_us_etf_screen_items(group, etf_rows, listing_map)
            stock_limit = (
                BROAD_NASDAQ_PREFILTER_LIMIT
                if group == "Nasdaq"
                else BROAD_NYSE_PREFILTER_LIMIT
            )
            universe[group] = merge_candidate_universe(
                stocks[:stock_limit]
                + etfs[:BROAD_US_ETF_PREFILTER_LIMIT]
                + universe.get(group, [])
            )
    except Exception as exc:
        print(f"Broad candidate universe failed, using curated list: {type(exc).__name__}: {exc}", file=sys.stderr)
    return universe


def build_b3_screen_items():
    items = []
    for ticker, sector, quality, ai in B3_BROAD_TICKERS:
        context_sector = sector or "B3"
        item = {
            "ticker": ticker,
            "symbol": f"{ticker}.SA",
            "name": candidate_company_name(ticker),
            "sector": context_sector,
            "quality": quality,
            "ai": ai,
            "catalyst": B3_SECTOR_CATALYSTS.get(
                context_sector,
                "resultado, caixa, margem e revisão de consenso",
            ),
            "risk": B3_SECTOR_RISKS.get(
                context_sector,
                "execução, liquidez, governança e revisão negativa de lucros",
            ),
            "turnaround": ticker in B3_TURNAROUND_TICKERS,
            "cyclical": ticker in B3_CYCLICAL_TICKERS,
            "_prefilter_score": b3_prefilter_score(ticker, quality, ai, context_sector),
        }
        items.append(item)
    return sorted(items, key=lambda item: item["_prefilter_score"], reverse=True)


def b3_prefilter_score(ticker, quality, ai, sector):
    score = quality * 0.48 + ai * 0.24
    if ticker in B3_TURNAROUND_TICKERS:
        score += 4.0
    if ticker in B3_CYCLICAL_TICKERS:
        score += 2.0
    if sector in {"Bancos", "Utilidades", "Energia", "Mineração"}:
        score += 2.5
    if sector in {"Educação", "Construção", "Varejo", "Saúde"}:
        score += 1.5
    return score


def fetch_us_listing_map():
    listing_map = {}
    nasdaq_rows = fetch_pipe_rows("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
    for row in nasdaq_rows:
        ticker = row.get("Symbol")
        if not ticker or row.get("Test Issue") == "Y":
            continue
        listing_map[ticker] = {
            "group": "Nasdaq",
            "name": row.get("Security Name", ""),
            "etf": row.get("ETF") == "Y",
        }
    other_rows = fetch_pipe_rows("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")
    for row in other_rows:
        ticker = row.get("ACT Symbol")
        if not ticker or row.get("Test Issue") == "Y":
            continue
        exchange = row.get("Exchange")
        if exchange in {"N", "P"}:
            group = "NYSE"
        elif exchange in {"A", "Z", "V"}:
            group = "NYSE"
        else:
            continue
        listing_map[ticker] = {
            "group": group,
            "name": row.get("Security Name", ""),
            "etf": row.get("ETF") == "Y",
        }
    return listing_map


def fetch_pipe_rows(url):
    page = fetch_url_text(url)
    if not page:
        return []
    lines = [
        line
        for line in page.splitlines()
        if line.strip() and not line.startswith("File Creation")
    ]
    if not lines:
        return []
    reader = csv.DictReader(lines, delimiter="|")
    return list(reader)


def fetch_stockanalysis_payload(url):
    page = fetch_url_text(url)
    if not page:
        return []
    match = re.search(r"count:\d+,data:\[", page)
    if not match:
        return []
    start = match.end() - 1
    end = find_js_array_end(page, start)
    if end is None:
        return []
    payload = page[start:end]
    payload = re.sub(r"([{,])([A-Za-z_][A-Za-z0-9_]*):", r'\1"\2":', payload)
    payload = re.sub(r":-\.(\d+)", r":-0.\1", payload)
    payload = re.sub(r":\.(\d+)", r":0.\1", payload)
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return []


def fetch_url_text(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def find_js_array_end(text_value, start):
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text_value)):
        char = text_value[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return idx + 1
    return None


def build_us_stock_screen_items(group, rows, listing_map):
    items = []
    for row in rows:
        ticker = row.get("s")
        listing = listing_map.get(ticker)
        if not listing or listing.get("group") != group or listing.get("etf"):
            continue
        if not is_candidate_common_stock(ticker, listing.get("name", row.get("n", ""))):
            continue
        price = number_or_none(row.get("price"))
        volume = number_or_none(row.get("volume"))
        market_cap = number_or_none(row.get("marketCap"))
        pe = number_or_none(row.get("peRatio"))
        if price is None or price < 5 or volume is None or volume < 250_000:
            continue
        if market_cap is None or market_cap < 500_000_000:
            continue
        item = {
            "ticker": ticker,
            "symbol": yahoo_symbol_for_us(ticker),
            "name": row.get("n") or listing.get("name") or ticker,
            "sector": row.get("industry") or "US listed",
            "quality": broad_stock_quality_score(row),
            "ai": broad_stock_ai_score(row),
            "catalyst": broad_stock_catalyst(row),
            "risk": broad_stock_risk(row),
            "multiples": (
                f"P/E {format_us_multiple(pe)} | "
                "FWRD P/E 0.00 | EV/EBITDA 0.00 | PEG Ratio 0.00"
            ),
            "_prefilter_score": broad_stock_prefilter_score(row),
        }
        items.append(item)
    return sorted(items, key=lambda item: item["_prefilter_score"], reverse=True)


def build_us_etf_screen_items(group, rows, listing_map):
    items = []
    for row in rows:
        ticker = row.get("s")
        listing = listing_map.get(ticker)
        if not listing or listing.get("group") != group or not listing.get("etf"):
            continue
        name = row.get("n") or listing.get("name") or ticker
        if not is_candidate_etf(name):
            continue
        price = number_or_none(row.get("price"))
        volume = number_or_none(row.get("volume"))
        aum = number_or_none(row.get("aum"))
        if price is None or price < 5 or volume is None or volume < 150_000:
            continue
        if aum is None or aum < 250_000_000:
            continue
        asset_class = row.get("assetClass") or "ETF"
        item = {
            "ticker": ticker,
            "symbol": yahoo_symbol_for_us(ticker),
            "name": name,
            "sector": f"ETF {asset_class}",
            "quality": broad_etf_quality_score(row),
            "ai": broad_etf_ai_score(row),
            "etf": True,
            "etf_value": broad_etf_value_score(row),
            "catalyst": f"fluxo para {asset_class.lower()}, liquidez e retomada do tema",
            "risk": "volatilidade temática, liquidez e composição da cesta",
            "multiples": "P/E 0.00 | FWRD P/E 0.00 | EV/EBITDA 0.00 | PEG Ratio 0.00",
            "_prefilter_score": broad_etf_prefilter_score(row),
        }
        items.append(item)
    return sorted(items, key=lambda item: item["_prefilter_score"], reverse=True)


def merge_candidate_universe(items):
    merged = []
    seen = set()
    for item in items:
        ticker = item.get("ticker")
        if not ticker or ticker in seen:
            continue
        clean_item = dict(item)
        clean_item.pop("_prefilter_score", None)
        merged.append(clean_item)
        seen.add(ticker)
    return merged


def is_candidate_common_stock(ticker, name):
    if not ticker or not name:
        return False
    if re.search(r"[\^/]", ticker):
        return False
    lowered = name.lower()
    excluded = [
        "warrant",
        "right",
        "unit",
        "preferred",
        "preference",
        "depositary share",
        "note due",
        "notes due",
        "bond",
        "debenture",
        "closed-end",
    ]
    return not any(term in lowered for term in excluded)


def is_candidate_etf(name):
    lowered = (name or "").lower()
    if "etf" not in lowered and "fund" not in lowered and "trust" not in lowered:
        return False
    excluded = [
        "2x",
        "3x",
        "4x",
        "leveraged",
        "inverse",
        "bear",
        "short",
        "ultrashort",
        "daily bull",
        "daily bear",
        "single stock",
        "autocallable",
    ]
    return not any(term in lowered for term in excluded)


def broad_stock_prefilter_score(row):
    pe = number_or_none(row.get("peRatio"))
    market_cap = number_or_none(row.get("marketCap")) or 0
    volume = number_or_none(row.get("volume")) or 0
    change = number_or_none(row.get("change")) or 0
    pe_score = metric_inverse_score(pe, 5, 24) if pe is not None else 18
    liquidity = clamp(math.log10(volume + 1) * 9, 0, 100)
    size = clamp(math.log10(market_cap + 1) * 6, 0, 100)
    pullback = clamp(max(0, -change) * 2.5, 0, 15)
    return pe_score * 0.55 + liquidity * 0.20 + size * 0.15 + pullback


def broad_etf_prefilter_score(row):
    aum = number_or_none(row.get("aum")) or 0
    volume = number_or_none(row.get("volume")) or 0
    holdings = number_or_none(row.get("holdings")) or 0
    change = number_or_none(row.get("change")) or 0
    liquidity = clamp(math.log10(volume + 1) * 10, 0, 100)
    scale = clamp(math.log10(aum + 1) * 6, 0, 100)
    diversification = clamp(math.log10(holdings + 1) * 18, 0, 100)
    pullback = clamp(max(0, -change) * 3, 0, 20)
    return liquidity * 0.35 + scale * 0.30 + diversification * 0.15 + pullback


def broad_stock_quality_score(row):
    market_cap = number_or_none(row.get("marketCap")) or 0
    volume = number_or_none(row.get("volume")) or 0
    return clamp(35 + math.log10(market_cap + 1) * 3 + math.log10(volume + 1) * 2)


def broad_stock_ai_score(row):
    pe = number_or_none(row.get("peRatio"))
    return clamp(45 + (score_candidate_multiples(f"P/E {format_us_multiple(pe)}") - 50) * 0.35)


def broad_etf_quality_score(row):
    aum = number_or_none(row.get("aum")) or 0
    volume = number_or_none(row.get("volume")) or 0
    return clamp(38 + math.log10(aum + 1) * 3 + math.log10(volume + 1) * 2)


def broad_etf_ai_score(row):
    return clamp(broad_etf_prefilter_score(row) * 0.75)


def broad_etf_value_score(row):
    return clamp(40 + broad_etf_prefilter_score(row) * 0.45)


def broad_stock_catalyst(row):
    industry = (row.get("industry") or "setor").lower()
    return f"rerating em {industry}, melhora de resultados e revisão de consenso"


def broad_stock_risk(row):
    industry = (row.get("industry") or "setor").lower()
    return f"ciclo de {industry}, execução e revisão negativa de lucros"


def yahoo_symbol_for_us(ticker):
    return (ticker or "").replace(".", "-")


def number_or_none(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_us_multiple(value):
    number = number_or_none(value)
    return f"{number:.2f}" if number is not None else "0.00"


def latest_summary_candidate_snapshot(ticker, out_dir=None):
    output_dir = Path(out_dir) if out_dir else OUT_DIR
    files = sorted(output_dir.glob("*summary-*.html"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files:
        snapshot = summary_candidate_snapshot_from_html(path, ticker)
        if snapshot:
            snapshot["source"] = str(path)
            return snapshot
    return None


def summary_candidate_snapshot_from_html(path, ticker):
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    marker = f"candidate-symbol'>{html.escape(ticker)}"
    start = text.find(marker)
    if start < 0:
        return None
    row_start = text.rfind("<tr", 0, start)
    row_end = text.find("</tr>", start)
    if row_start < 0 or row_end < 0:
        return None
    row = html.unescape(text[row_start : row_end + 5])
    return {
        "price": extract_summary_money(row, r"class='current-price'>([^<]+)<"),
        "consensus": extract_summary_money(row, r"class='target-price'>([^<]+)<"),
        "our_tp": extract_summary_money(row, r"class='model-target-price'>([^<]+)<"),
        "buy_in": extract_summary_money(row, r"class='buy-price'>([^<]+)<"),
        "analysts": extract_summary_int(row, r"\((\d+)\s+analistas\)"),
    }


def extract_summary_money(text, pattern):
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    return normalize_summary_number(match.group(1))


def extract_summary_int(text, pattern):
    match = re.search(pattern, text, re.I)
    return int(match.group(1)) if match else None


def normalize_summary_number(value):
    cleaned = re.sub(r"[^0-9,.-]", "", str(value or ""))
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def build_dynamic_candidate_stocks():
    CANDIDATE_BASE_CACHE.clear()
    universe_by_group = build_candidate_screening_universe()
    dynamic_groups = {}
    for group, universe in universe_by_group.items():
        scored_items = []
        watchlist_items = []
        prepared_items = [prepare_dynamic_candidate_item(raw_item) for raw_item in universe]
        preload_candidate_quote_cache(prepared_items)
        max_workers = max(1, min(CANDIDATE_SNAPSHOT_WORKERS, len(prepared_items) or 1))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(score_prepared_candidate_item, item)
                for item in prepared_items
            ]
            for future in as_completed(futures):
                result = future.result()
                if result is None:
                    continue
                strict_entry, watchlist_entry = result
                if strict_entry is not None:
                    scored_items.append(strict_entry)
                elif watchlist_entry is not None:
                    watchlist_items.append(watchlist_entry)
        selection_pool = select_dynamic_candidate_group(
            scored_items,
            limit=CANDIDATE_FINAL_REVIEW_LIMITS.get(group, 200),
            group=group,
            watchlist_items=watchlist_items,
        )
        enriched_items = [item for _, item in selection_pool]
        for item in enriched_items:
            enrich_selected_candidate_snapshot(item)
        selected_items = [
            item
            for item in enriched_items
            if candidate_final_display_eligible(item)
        ]
        display_limit = CANDIDATE_DISPLAY_LIMITS.get(group, 5)
        selected_items = sorted(selected_items, key=candidate_final_selection_sort_key)[:display_limit]
        dynamic_groups[group] = selected_items
    return dynamic_groups


def score_prepared_candidate_item(item):
    try:
        base = candidate_base_snapshot(item)
        score = score_dynamic_candidate(item, base)
        if score is not None:
            item["candidate_status"] = "Full Match"
            item["multiples"] = base.get("multiples") or item.get("multiples", "")
            item["thesis"] = dynamic_candidate_thesis(item, base, score)
            item["risk"] = dynamic_candidate_risk(item)
            item["score"] = score["total"]
            return (score, item), None
        watchlist_score = score_dynamic_candidate(item, base, watchlist=True)
        if watchlist_score is None:
            return None
        item["candidate_status"] = "Watchlist"
        item["multiples"] = base.get("multiples") or item.get("multiples", "")
        item["thesis"] = dynamic_candidate_thesis(item, base, watchlist_score)
        item["risk"] = dynamic_candidate_risk(item)
        item["score"] = watchlist_score["total"]
        return None, (watchlist_score, item)
    except Exception as exc:
        print(
            f"Candidate snapshot failed for {item.get('ticker', 'N/D')}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None


def preload_candidate_quote_cache(items):
    symbols = []
    for item in items:
        ticker = item.get("ticker")
        symbol = CANDIDATE_SYMBOLS.get(ticker, item.get("symbol", ticker))
        if symbol:
            symbols.append(symbol)
    fetch_yahoo_quote_batch(symbols)


def candidate_screening_multiples(item, symbol):
    multiples = item.get("multiples")
    if multiples:
        return multiples
    if item.get("etf"):
        return "P/E N/A | FWRD P/E N/A | EV/EBITDA N/A | PEG Ratio N/A"
    sector = normalize_ws(str(item.get("sector", ""))).lower()
    if symbol.endswith(".SA"):
        if "banco" in sector or "financeiro" in sector:
            return "P/E 8.50 | FWRD P/E 7.80 | EV/EBITDA 0.00 | PEG Ratio 0.90"
        if "utilidade" in sector or "energia" in sector or "saneamento" in sector:
            return "P/E 12.00 | FWRD P/E 10.80 | EV/EBITDA 7.50 | PEG Ratio 1.15"
        if "minera" in sector or "papel" in sector or "commod" in sector:
            return "P/E 9.50 | FWRD P/E 8.40 | EV/EBITDA 5.80 | PEG Ratio 0.95"
        if "varejo" in sector or "constru" in sector or "saúde" in sector or "educa" in sector:
            return "P/E 15.00 | FWRD P/E 12.50 | EV/EBITDA 8.50 | PEG Ratio 1.25"
        return "P/E 13.00 | FWRD P/E 11.50 | EV/EBITDA 8.00 | PEG Ratio 1.15"
    return "P/E 18.00 | FWRD P/E 15.50 | EV/EBITDA 11.50 | PEG Ratio 1.20"


def enrich_selected_candidate_snapshot(item):
    ticker = item.get("ticker")
    symbol = CANDIDATE_SYMBOLS.get(ticker, item.get("symbol", ticker))
    base = CANDIDATE_BASE_CACHE.get(ticker, {})
    current_price = base.get("current_price")
    consensus_target_value = base.get("consensus_target_value")
    price_context = base.get("price_context") or {}
    multiples = fetch_candidate_multiples(ticker, symbol, item.get("multiples", ""))
    model = candidate_modeled_target_snapshot(
        item,
        current_price,
        consensus_target_value,
        multiples,
        price_context,
    )
    target_value = model.get("target_value") or consensus_target_value
    upside_pct = candidate_upside_pct(current_price, target_value)
    buy_in_value = None
    distance = None
    if current_price is not None and upside_pct is not None and upside_pct >= MIN_CANDIDATE_UPSIDE_PCT:
        buy_in_value = candidate_buy_in_value(ticker, current_price, target_value, price_context, multiples)
        distance = candidate_buy_in_distance_pct(current_price, buy_in_value)
    base.update(
        {
            "multiples": multiples,
            "target": model.get("target_display") or format_candidate_model_target_price(symbol, target_value),
            "target_value": target_value,
            "model_target": model.get("target_display") or format_candidate_model_target_price(symbol, target_value),
            "model_target_value": target_value,
            "model_target_methods": model.get("methods", {}),
            "upside_pct": upside_pct,
            "buy_in_value": buy_in_value,
            "buy_in_distance_pct": distance,
            "price_context": price_context,
        }
    )
    CANDIDATE_BUY_IN_ANALYSIS[ticker] = dynamic_buy_in_analysis(item, base)
    CANDIDATE_BASE_CACHE[ticker] = base
    item["multiples"] = multiples


def prepare_dynamic_candidate_item(raw_item):
    item = dict(raw_item)
    ticker = item["ticker"]
    symbol = item.get("symbol", ticker)
    CANDIDATE_SYMBOLS[ticker] = symbol
    CANDIDATE_IS_ETF[ticker] = bool(item.get("etf"))
    if item.get("name"):
        CANDIDATE_NAMES[ticker] = item["name"]

    required_upside = 0.30
    buy_discount = 0.09
    if item.get("etf"):
        required_upside += 0.02
        buy_discount += 0.01
    if item.get("china"):
        required_upside += 0.08
        buy_discount += 0.03
    if item.get("turnaround"):
        required_upside += 0.07
        buy_discount += 0.03
    if item.get("cyclical"):
        required_upside += 0.03
        buy_discount += 0.02

    CANDIDATE_REQUIRED_UPSIDE[ticker] = required_upside
    CANDIDATE_BUY_IN_DISCOUNT[ticker] = buy_discount
    return item


def candidate_base_snapshot(item):
    ticker = item["ticker"]
    symbol = CANDIDATE_SYMBOLS.get(ticker, item.get("symbol", ticker))
    if ticker in CANDIDATE_BASE_CACHE:
        return CANDIDATE_BASE_CACHE[ticker]

    current_price = fetch_latest_market_price(symbol)
    daily_change_pct = fetch_candidate_daily_change_pct(symbol, current_price)
    consensus_display, consensus_target_value = fetch_candidate_target_price(ticker)
    has_consensus = candidate_has_consensus_analysts(consensus_display, consensus_target_value)
    if symbol.endswith(".SA") and not has_consensus:
        consensus_display = "No public consensus"
    target_static_fallback = candidate_is_static_target_fallback(
        ticker,
        symbol,
        consensus_display,
        consensus_target_value,
    )
    price_context = {}
    multiples = candidate_screening_multiples(item, symbol)
    model = {}
    target_value = None
    if current_price is not None:
        model = candidate_modeled_target_snapshot(
            item,
            current_price,
            consensus_target_value,
            multiples,
            price_context,
        )
        target_value = model.get("target_value")
    if target_value is None:
        target_value = consensus_target_value
    upside_pct = candidate_upside_pct(current_price, target_value)
    price_context = {}
    buy_in_value = None
    distance = None
    if current_price is not None and upside_pct is not None and upside_pct >= MIN_CANDIDATE_UPSIDE_PCT:
        buy_in_value = candidate_buy_in_value(ticker, current_price, target_value, price_context, multiples)
        distance = candidate_buy_in_distance_pct(current_price, buy_in_value)
    snapshot = {
        "current_price": current_price,
        "daily_change_pct": daily_change_pct,
        "consensus": consensus_display,
        "consensus_target_value": consensus_target_value,
        "has_public_consensus": has_consensus,
        "target_static_fallback": target_static_fallback,
        "target": model.get("target_display") or format_candidate_model_target_price(symbol, target_value),
        "target_value": target_value,
        "model_target": model.get("target_display") or format_candidate_model_target_price(symbol, target_value),
        "model_target_value": target_value,
        "model_target_methods": model.get("methods", {}),
        "consensus_upside_pct": candidate_upside_pct(current_price, consensus_target_value),
        "upside_pct": upside_pct,
        "price_context": price_context,
        "buy_in_value": buy_in_value,
        "buy_in_distance_pct": distance,
        "multiples": multiples,
    }
    CANDIDATE_BUY_IN_ANALYSIS[ticker] = dynamic_buy_in_analysis(item, snapshot)
    CANDIDATE_BASE_CACHE[ticker] = snapshot
    return snapshot


def score_dynamic_candidate(item, base, watchlist=False):
    if base.get("current_price") is None:
        return None
    ticker = item.get("ticker", "")
    symbol = CANDIDATE_SYMBOLS.get(ticker, item.get("symbol", ticker))
    is_b3 = str(symbol or "").endswith(".SA")
    has_consensus = bool(base.get("has_public_consensus")) or candidate_has_consensus_analysts(
        base.get("consensus"),
        base.get("consensus_target_value"),
    )
    if not has_consensus and not is_b3:
        return None

    upside_pct = base.get("upside_pct")
    if upside_pct is None or upside_pct < MIN_CANDIDATE_UPSIDE_PCT:
        return None
    buy_in_distance = base.get("buy_in_distance_pct")
    if (
        buy_in_distance is None
        or buy_in_distance < MIN_WATCHLIST_BUY_IN_DISTANCE_PCT
        or buy_in_distance >= MAX_WATCHLIST_BUY_IN_DISTANCE_PCT
    ):
        return None
    strict_buy_in = (
        MIN_CANDIDATE_BUY_IN_DISTANCE_PCT
        <= buy_in_distance
        < MAX_CANDIDATE_BUY_IN_DISTANCE_PCT
    )
    if watchlist:
        if strict_buy_in:
            return None
    elif not strict_buy_in:
        return None
    upside_score = clamp(((upside_pct or 0) - 15) / 85 * 100)
    valuation_score = (
        clamp(item.get("etf_value", 50))
        if item.get("etf")
        else score_candidate_multiples(base.get("multiples"))
    )
    timing_score = score_buy_in_timing(base.get("buy_in_distance_pct"))
    daily_setup_score = score_candidate_daily_setup(base.get("daily_change_pct"))
    if not has_consensus:
        source_score = 30
    elif base.get("target_static_fallback"):
        source_score = 45
    else:
        source_score = 78
    quality_score = clamp(item.get("quality", 50))
    ai_score = clamp(item.get("ai", 50))
    penalty = 0
    if base.get("target_value") is None:
        penalty += 18
    if not has_consensus:
        penalty += 8
    if base.get("target_static_fallback"):
        penalty += 4
    if item.get("china"):
        penalty += 8
    if item.get("turnaround"):
        penalty += 5
    if item.get("cyclical"):
        penalty += 3

    total = (
        upside_score * 0.30
        + valuation_score * 0.25
        + timing_score * 0.15
        + quality_score * 0.12
        + daily_setup_score * 0.10
        + source_score * 0.04
        + ai_score * 0.04
        - penalty
    )
    if watchlist:
        total -= 12
    return {
        "total": total,
        "upside_pct": upside_pct,
        "upside_score": upside_score,
        "valuation_score": valuation_score,
        "timing_score": timing_score,
        "daily_setup_score": daily_setup_score,
        "source_score": source_score,
        "watchlist": watchlist,
    }


def candidate_is_static_target_fallback(ticker, symbol, display, value):
    if not str(symbol or "").endswith(".SA"):
        return False
    fallback_display, fallback_value = candidate_target_fallback(ticker)
    if fallback_value is None or value is None:
        return False
    return (
        normalize_ws(str(display or "")) == normalize_ws(str(fallback_display or ""))
        and abs(float(value) - float(fallback_value)) < 0.001
    )


def score_candidate_daily_setup(daily_change_pct):
    if daily_change_pct is None:
        return 50
    change = float(daily_change_pct)
    if -3.0 <= change <= 1.5:
        return 82
    if -6.0 <= change < -3.0:
        return 68
    if 1.5 < change <= 4.0:
        return 58
    if -9.0 <= change < -6.0:
        return 42
    if change > 4.0:
        return 35
    return 30


def select_dynamic_candidate_group(scored_items, limit=5, group=None, watchlist_items=None):
    ranked = sorted(scored_items, key=candidate_selection_score_sort_key)
    selected = ranked[:limit]
    if len(selected) >= limit:
        return selected
    selected_tickers = {item.get("ticker") for _, item in selected}
    watchlist_ranked = sorted(watchlist_items or [], key=candidate_selection_score_sort_key)
    for entry in watchlist_ranked:
        _, item = entry
        ticker = item.get("ticker")
        if not ticker or ticker in selected_tickers:
            continue
        selected.append(entry)
        selected_tickers.add(ticker)
        if len(selected) >= limit:
            break
    return selected


def candidate_selection_score_sort_key(entry):
    score, item = entry
    total = score.get("total")
    upside = score.get("upside_pct")
    if total is None:
        return (1, 0, 0, item.get("ticker", ""))
    return (0, -total, -(upside or 0), item.get("ticker", ""))


def candidate_selection_upside_sort_key(entry):
    score, item = entry
    upside = score.get("upside_pct")
    if upside is None:
        return (1, 0, item.get("ticker", ""))
    return (0, -upside, item.get("ticker", ""))


def candidate_final_display_eligible(item):
    ticker = item.get("ticker")
    base = CANDIDATE_BASE_CACHE.get(ticker, {})
    upside = base.get("upside_pct")
    distance = base.get("buy_in_distance_pct")
    if upside is None or upside < MIN_CANDIDATE_UPSIDE_PCT:
        return False
    if distance is None:
        return False
    return (
        MIN_CANDIDATE_BUY_IN_DISTANCE_PCT
        <= distance
        < MAX_CANDIDATE_BUY_IN_DISTANCE_PCT
    )


def candidate_final_selection_sort_key(item):
    ticker = item.get("ticker")
    base = CANDIDATE_BASE_CACHE.get(ticker, {})
    score = item.get("score")
    upside = base.get("upside_pct")
    distance = base.get("buy_in_distance_pct")
    timing_penalty = abs(distance or 0) * 0.08
    if score is None:
        return (1, 0, 0, ticker or "")
    return (0, -(score - timing_penalty), -(upside or 0), ticker or "")


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def score_candidate_multiples(multiples):
    values = candidate_multiples_numeric(multiples)
    scores = [
        metric_inverse_score(values.get("P/E"), 6, 24),
        metric_inverse_score(values.get("FWRD P/E"), 5, 20),
        metric_inverse_score(values.get("EV/EBITDA"), 4, 14),
        metric_inverse_score(values.get("PEG Ratio"), 0.35, 1.8),
    ]
    usable = [score for score in scores if score is not None]
    return sum(usable) / len(usable) if usable else 20


def candidate_multiples_numeric(multiples):
    return {
        label: parse_multiple_value(value)
        for label, value in parse_candidate_multiples(multiples)
    }


def parse_multiple_value(value):
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw.upper() in {"N/D", "N/A", "NA", "-"}:
        return None
    cleaned = re.sub(r"[^0-9,.\-]", "", raw)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def metric_inverse_score(value, best, worst):
    if value is None:
        return 18
    if value <= 0:
        return 10
    if value <= best:
        return 100
    if value >= worst:
        return 15
    return 100 - ((value - best) / (worst - best) * 85)


def score_buy_in_timing(distance_pct):
    if distance_pct is None:
        return 30
    if distance_pct < -12:
        return 66
    if distance_pct < -6:
        return 82
    if distance_pct <= 0:
        return 96
    if distance_pct <= 2:
        return 100
    if distance_pct <= 5:
        return 92
    if distance_pct <= 10:
        return 78
    if distance_pct <= 18:
        return 58
    if distance_pct <= 30:
        return 35
    return 18


def dynamic_candidate_thesis(item, base, score):
    catalyst = item.get("catalyst", "rerating operacional")
    return (
        f"{qualitative_candidate_context(item)} "
        f"Gatilho: {catalyst}."
    )


def dynamic_candidate_risk(item):
    risk = item.get("risk", "execução, liquidez e revisão de premissas")
    if item.get("china"):
        return f"{risk}; regulação/sentimento podem pesar."
    if item.get("etf"):
        return f"{risk}; tese depende do tema inteiro, nao de uma empresa isolada."
    if item.get("turnaround"):
        return f"{risk}; precisa provar melhora operacional."
    if item.get("cyclical"):
        return f"{risk}; ciclo pode virar antes da melhora."
    return f"{risk}; monitorar margens, caixa e governança."


def qualitative_candidate_context(item):
    ticker = item.get("ticker", "")
    sector = item.get("sector", "")
    overrides = {
        "COGN3": "Recuperação em educação: captação e retenção precisam virar margem e caixa.",
        "MRVE3": "Construção cíclica: juros menores e MCMV podem aliviar caixa e vendas.",
        "YDUQ3": "Normalização em educação: inadimplência e dívida precisam cair.",
        "CYRE3": "Qualidade imobiliária: execução e marca capturam queda de juros.",
        "TOTS3": "Franquia defensiva: recorrência e cross-sell sustentam crescimento.",
        "PETR4": "Geração de caixa: dividendos precisam compensar risco estatal.",
        "ITUB4": "Banco premium: ROE e crédito sustentam posição em fraquezas.",
        "CHTR": "Desalavancagem: FCF precisa reduzir dívida e estabilizar banda larga.",
        "PDD": "Crescimento com execução: Temu deve crescer sem sacrificar margem.",
        "TCOM": "Viagens em recuperação: demanda chinesa sustenta alavanca operacional.",
        "META": "Plataforma dominante: ads, IA e eficiência precisam superar capex.",
        "ADBE": "Software premium: IA precisa proteger Creative Cloud e preço.",
        "TME": "Consumo digital chinês: assinaturas e ARPU podem ampliar margem.",
        "FUTU": "Plataforma financeira: melhora em China/HK destrava atividade.",
        "CRM": "Franquia SaaS madura: margem, IA e retorno de capital precisam compensar crescimento menor.",
        "CHWY": "Varejo pet digital: recorrência e margem são mais importantes que crescimento bruto.",
        "BILL": "Software financeiro em recuperação: crescimento e margem precisam voltar juntos.",
        "RBLX": "Plataforma social de jogos: tese depende de monetizar engajamento sem perder crescimento.",
        "FMC": "Agroquímicos em virada: fim do destocking precisa aparecer em volumes, preço e caixa.",
        "OXY": "Energia disciplinada: desalavancagem depende de petróleo favorável.",
        "VZ": "Telecom defensiva: FCF e dividendos importam mais que crescimento.",
        "IBIT": "ETF de bitcoin spot: captura fluxo institucional, mas exige disciplina por volatilidade.",
        "QQQ": "Nasdaq 100 diversificado: qualidade das megacaps precisa compensar concentração.",
        "SMH": "ETF de semicondutores: AI e data centers sustentam demanda, com alto beta setorial.",
        "SOXX": "Semicondutores amplos: bom veículo para ciclo de chips sem escolher uma única empresa.",
        "CIBR": "Cybersecurity diversificado: gasto recorrente em segurança dá resiliência ao tema.",
        "ICLN": "Energia limpa em recuperação: tese depende de juros menores e melhora de margens.",
        "KWEB": "Internet chinesa via ETF: reduz risco de single name, mas mantém risco China.",
        "ARKF": "Fintech temática: melhora em juros e apetite a growth pode reprecificar a cesta.",
        "FINX": "Fintech global: pagamentos e software financeiro oferecem crescimento com diversificação.",
        "BKCH": "Blockchain via ETF: captura ciclo cripto com diversificação entre empresas do tema.",
        "GDX": "Mineradoras de ouro: alavanca operacional ao ouro sem concentrar em uma mineradora.",
        "GDXJ": "Junior gold miners: maior beta ao ouro, exigindo sizing conservador.",
        "SLV": "Prata via ETF: exposição direta ao metal, sem risco operacional de mineradora.",
        "ARKK": "Innovation/growth: cesta de nomes disruptivos precisa de juros e liquidez favoráveis.",
    }
    if ticker in overrides:
        return overrides[ticker]
    if item.get("turnaround"):
        return f"Recuperação em {sector.lower() or 'setor cíclico'}: execução precisa aparecer em margem e caixa."
    if item.get("etf"):
        return f"ETF temático em {sector.lower() or 'tema selecionado'}: entrada depende de fluxo, tendência e desconto."
    if item.get("china"):
        return "Assimetria em China/ADR: fundamentos precisam superar risco macro/regulatório."
    if item.get("cyclical"):
        return f"Cíclica em {sector.lower() or 'setor sensível'}: entrada depende de inflexão de demanda."
    if item.get("quality", 50) >= 80:
        return f"Qualidade em {sector.lower() or 'franquia forte'}: comprar só com margem de segurança."
    return f"Tese operacional em {sector.lower() or 'empresa selecionada'}: gatilhos precisam aparecer nos resultados."


def qualitative_timing_context(base):
    distance = base.get("buy_in_distance_pct")
    if distance is None:
        return "Aguardar confirmação de preço e liquidez antes de agir."
    if distance < -6:
        return "Já negocia abaixo do buy-in; a decisão depende mais da qualidade da tese e do risco do que de preço."
    if distance <= 3:
        return "Está perto da zona de entrada, então a confirmação qualitativa pesa mais que esperar grande queda."
    if distance <= 10:
        return "Ainda pede disciplina: esperar pullback ou notícia operacional que aumente convicção."
    return "Monitorar sem pressa; hoje a entrada exige desconto maior ou melhora clara da tese."


def describe_candidate_valuation(multiples):
    values = candidate_multiples_numeric(multiples)
    highlights = []
    fwrd = values.get("FWRD P/E")
    ev_ebitda = values.get("EV/EBITDA")
    peg = values.get("PEG Ratio")
    if fwrd is not None and 0 < fwrd <= 14:
        highlights.append(f"FWRD P/E {fwrd:.1f}x")
    if ev_ebitda is not None and 0 < ev_ebitda <= 10:
        highlights.append(f"EV/EBITDA {ev_ebitda:.1f}x")
    if peg is not None and 0 < peg <= 1.2:
        highlights.append(f"PEG {peg:.1f}x")
    if highlights:
        return "múltiplos atrativos (" + ", ".join(highlights[:2]) + ")"
    return "valuation mais barato que o prêmio de qualidade/recuperação sugere"


def dynamic_buy_in_analysis(item, base):
    distance = base.get("buy_in_distance_pct")
    catalyst = shorten_candidate_text(item.get("catalyst", "gatilho operacional"), 42)
    if distance is None:
        return f"Aguardar dados mais claros; gatilho: {catalyst}."
    if item.get("etf"):
        if distance < -6:
            return f"Abaixo do buy-in; reforçar só se fluxo e tendência confirmarem."
        if distance <= 3:
            return f"ETF perto da entrada; confirmar fluxo e tendência do tema."
        if distance <= 8:
            return f"Aguardar pullback curto; comprar apenas com melhora do tema."
        return f"Esperar aproximação do buy-in antes de aumentar exposição temática."
    if distance < -6:
        return f"Abaixo do buy-in; validar risco e {catalyst} antes de agir."
    if distance <= 3:
        return f"Zona de entrada; confirmar {catalyst}."
    if distance <= 8:
        return f"Aguardar pullback curto e confirmar {catalyst}."
    if distance <= 15:
        return f"Esperar melhor preço; entrada só se voltar ao buy-in."
    return f"Distante do buy-in; monitorar queda ou revisão positiva da tese."


def build_candidate_stock_data():
    data = {}
    for group_items in CHEAP_STOCKS.values():
        for item in group_items:
            ticker = item["ticker"]
            symbol = CANDIDATE_SYMBOLS.get(ticker, ticker)
            base = CANDIDATE_BASE_CACHE.get(ticker, {})
            current_price = base.get("current_price")
            if current_price is None and "current_price" not in base:
                current_price = fetch_latest_market_price(symbol)
            daily_change_pct = base.get("daily_change_pct")
            if daily_change_pct is None and "daily_change_pct" not in base:
                daily_change_pct = fetch_candidate_daily_change_pct(symbol, current_price)
            if "consensus" in base:
                consensus_display = base.get("consensus", "N/D")
                consensus_target_value = base.get("consensus_target_value")
            else:
                consensus_display, consensus_target_value = fetch_candidate_target_price(ticker)
            price_context = base.get("price_context")
            if price_context is None:
                price_context = fetch_candidate_price_context(symbol)
            multiples = base.get("multiples") or fetch_candidate_multiples(ticker, symbol, item.get("multiples", ""))
            if "model_target" in base:
                model_target_display = base.get("model_target", "N/D")
                target_value = base.get("model_target_value") or base.get("target_value")
                model_methods = base.get("model_target_methods", {})
            else:
                model = candidate_modeled_target_snapshot(
                    item,
                    current_price,
                    consensus_target_value,
                    multiples,
                    price_context,
                )
                model_target_display = model.get("target_display", "N/D")
                target_value = model.get("target_value") or consensus_target_value
                model_methods = model.get("methods", {})
            buy_in_value = base.get("buy_in_value")
            if buy_in_value is None and "buy_in_value" not in base:
                buy_in_value = candidate_buy_in_value(ticker, current_price, target_value, price_context, multiples)
            data[ticker] = {
                "current_price": current_price,
                "daily_change_pct": daily_change_pct,
                "daily_change": format_signed_pct(daily_change_pct) if daily_change_pct is not None else "N/D",
                "price": format_candidate_stock_price(symbol, current_price) if current_price is not None else "N/D",
                "buy_in": format_candidate_buy_in(ticker, current_price, target_value, price_context, multiples),
                "buy_in_value": buy_in_value,
                "price_context": price_context,
                "buy_in_distance_pct": candidate_buy_in_distance_pct(current_price, buy_in_value),
                "price_to_buy_in": format_candidate_price_to_buy_in(ticker, current_price, target_value, price_context, multiples),
                "consensus": consensus_display,
                "consensus_target_value": consensus_target_value,
                "consensus_upside_pct": candidate_upside_pct(current_price, consensus_target_value),
                "target": model_target_display,
                "target_value": target_value,
                "model_target": model_target_display,
                "model_target_value": target_value,
                "model_target_methods": model_methods,
                "upside_pct": candidate_upside_pct(current_price, target_value),
                "upside": format_candidate_upside(current_price, target_value),
                "multiples": multiples,
            }
    return data


def fetch_latest_market_price(symbol):
    if symbol in YAHOO_QUOTE_CACHE:
        quote = YAHOO_QUOTE_CACHE.get(symbol) or {}
        price = quote.get("regularMarketPrice") or quote.get("regularMarketPreviousClose")
        price = number_or_none(price)
        if price is not None:
            return price
    meta = fetch_yahoo_chart_meta(symbol)
    price = meta.get("regularMarketPrice") or meta.get("previousClose")
    if price is not None:
        return price
    quote = fetch_yahoo_quote(symbol)
    return quote.get("regularMarketPrice") or quote.get("regularMarketPreviousClose")


def fetch_candidate_daily_change_pct(symbol, current_price=None):
    if symbol in YAHOO_QUOTE_CACHE:
        quote = YAHOO_QUOTE_CACHE.get(symbol) or {}
        pct = number_or_none(quote.get("regularMarketChangePercent"))
        if pct is not None:
            return pct
        price = number_or_none(current_price) or number_or_none(quote.get("regularMarketPrice"))
        previous = number_or_none(quote.get("regularMarketPreviousClose"))
        if price is not None and previous:
            return (price / previous - 1) * 100
    meta = fetch_yahoo_chart_meta(symbol)
    pct = number_or_none(meta.get("regularMarketChangePercent"))
    if pct is not None:
        return pct
    price = number_or_none(current_price) or number_or_none(meta.get("regularMarketPrice"))
    previous = number_or_none(meta.get("chartPreviousClose")) or number_or_none(meta.get("previousClose"))
    if price is not None and previous:
        return (price / previous - 1) * 100
    quote = fetch_yahoo_quote(symbol)
    pct = number_or_none(quote.get("regularMarketChangePercent"))
    if pct is not None:
        return pct
    previous = number_or_none(quote.get("regularMarketPreviousClose"))
    price = price or number_or_none(quote.get("regularMarketPrice"))
    if price is not None and previous:
        return (price / previous - 1) * 100
    return None


def fetch_yahoo_chart_meta(symbol):
    if symbol in YAHOO_CHART_META_CACHE:
        return YAHOO_CHART_META_CACHE[symbol]
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?range=1d&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload["chart"]["result"][0]
        meta = result.get("meta", {}) or {}
    except Exception:
        meta = {}
    YAHOO_CHART_META_CACHE[symbol] = meta
    return meta


def fetch_yahoo_quote(symbol):
    if symbol in YAHOO_QUOTE_CACHE:
        return YAHOO_QUOTE_CACHE[symbol]
    url = (
        "https://query1.finance.yahoo.com/v7/finance/quote?symbols="
        f"{urllib.parse.quote(symbol)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("quoteResponse", {}).get("result", [])
        quote = result[0] if result else {}
    except Exception:
        quote = {}
    YAHOO_QUOTE_CACHE[symbol] = quote
    return quote


def fetch_yahoo_quote_batch(symbols, chunk_size=60):
    unique_symbols = []
    seen = set()
    for symbol in symbols:
        if not symbol or symbol in seen or symbol in YAHOO_QUOTE_CACHE:
            continue
        unique_symbols.append(symbol)
        seen.add(symbol)
    for start in range(0, len(unique_symbols), chunk_size):
        chunk = unique_symbols[start : start + chunk_size]
        url = (
            "https://query1.finance.yahoo.com/v7/finance/quote?symbols="
            f"{urllib.parse.quote(','.join(chunk), safe=',')}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        found = set()
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            for quote in payload.get("quoteResponse", {}).get("result", []):
                symbol = quote.get("symbol")
                if not symbol:
                    continue
                YAHOO_QUOTE_CACHE[symbol] = quote
                found.add(symbol)
        except Exception:
            found = set()


def fetch_yahoo_price_history(symbol, range_value="6mo", interval="1d"):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?range={urllib.parse.quote(range_value)}&interval={urllib.parse.quote(interval)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        closes = [
            float(value)
            for value in quote.get("close", [])
            if value is not None and value > 0
        ]
        highs = [
            float(value)
            for value in quote.get("high", [])
            if value is not None and value > 0
        ]
        return {"closes": closes, "highs": highs}
    except Exception:
        return {"closes": [], "highs": []}


def fetch_candidate_price_context(symbol):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?range=6mo&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload["chart"]["result"][0]
        closes = [
            float(value)
            for value in result["indicators"]["quote"][0].get("close", [])
            if value is not None and value > 0
        ]
    except Exception:
        closes = []
    if not closes:
        return {}
    sorted_closes = sorted(closes)
    recent_20 = closes[-20:] if len(closes) >= 20 else closes
    recent_50 = closes[-50:] if len(closes) >= 50 else closes
    recent_100 = closes[-100:] if len(closes) >= 100 else closes
    return {
        "low_6m": min(closes),
        "high_6m": max(closes),
        "low_20d": min(recent_20),
        "high_20d": max(recent_20),
        "low_50d": min(recent_50),
        "high_50d": max(recent_50),
        "sma_20d": sum(recent_20) / len(recent_20),
        "sma_50d": sum(recent_50) / len(recent_50),
        "sma_100d": sum(recent_100) / len(recent_100),
        "percentile_10_6m": percentile(sorted_closes, 0.10),
        "percentile_25_6m": percentile(sorted_closes, 0.25),
        "percentile_35_6m": percentile(sorted_closes, 0.35),
        "percentile_50_6m": percentile(sorted_closes, 0.50),
        "percentile_rank_6m": percentile_rank(closes, closes[-1]),
        "volatility_20d": realized_volatility(recent_20),
    }


def percentile(sorted_values, pct):
    if not sorted_values:
        return None
    index = int(round((len(sorted_values) - 1) * pct))
    return sorted_values[max(0, min(len(sorted_values) - 1, index))]


def percentile_rank(values, value):
    if not values or value is None:
        return None
    below = sum(1 for item in values if item <= value)
    return below / len(values)


def realized_volatility(values):
    if len(values) < 3:
        return None
    returns = []
    for previous, current in zip(values, values[1:]):
        if previous > 0:
            returns.append((current / previous) - 1)
    if len(returns) < 2:
        return None
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance)


def fetch_candidate_target_price(ticker):
    symbol = CANDIDATE_SYMBOLS.get(ticker, ticker)
    if CANDIDATE_IS_ETF.get(ticker):
        return fetch_etf_consensus_target_price(symbol) or ("N/D", None)
    if symbol.endswith(".SA"):
        yahoo_target = fetch_yahoo_target_price(symbol, "R$")
        if yahoo_target and candidate_has_consensus_analysts(yahoo_target[0], yahoo_target[1]):
            return yahoo_target
        display, value = fetch_b3_target_price(ticker)
        if value is not None:
            return display, value
        return candidate_target_fallback(ticker)
    yahoo_target = fetch_yahoo_target_price(symbol, "US$")
    if yahoo_target and candidate_has_consensus_analysts(yahoo_target[0], yahoo_target[1]):
        return yahoo_target
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            page = response.read().decode("utf-8", errors="replace")
        target = re.search(r"average price target of\s+\$([0-9,.]+)", page, re.I)
        if not target:
            target = re.search(r"Price Target:\s*\$([0-9,.]+)", page, re.I)
        if not target:
            return candidate_target_fallback(ticker)
        value = float(target.group(1).rstrip(".").replace(",", ""))
        analysts = re.search(r"(\d+)\s+analysts.*?average price target", page, re.I | re.S)
        analyst_text = f" ({analysts.group(1)} anal.)" if analysts else ""
        return f"US$ {value:,.2f}{analyst_text}", value
    except Exception:
        return candidate_target_fallback(ticker)


def candidate_target_fallback(ticker):
    display = CANDIDATE_TARGETS.get(ticker, "N/D")
    return display, parse_candidate_target_display_value(display)


def parse_candidate_target_display_value(display):
    raw = normalize_ws(str(display or "")).split("(", 1)[0].strip()
    if not raw or raw == "N/D":
        return None
    if "R$" in raw:
        return parse_ptbr_number(raw.replace("R$", "").strip())
    cleaned = raw.replace("US$", "").replace("$", "").strip()
    return parse_us_number(cleaned)


def candidate_has_consensus_analysts(display, value):
    if value is None:
        return False
    return bool(re.search(r"\d+\s*anal", normalize_ws(str(display or "")), re.I))


def fetch_etf_consensus_target_price(symbol):
    target = fetch_yahoo_target_price(symbol, "US$")
    if target is None:
        return None
    display, value = target
    if value is None or "anal.)" not in display:
        return None
    return display, value


def fetch_yahoo_target_price(symbol, currency_prefix):
    quote = fetch_yahoo_quote(symbol)
    value = quote.get("targetMeanPrice") or quote.get("targetMedianPrice")
    if value is None:
        return None
    analysts = quote.get("numberOfAnalystOpinions")
    analyst_text = f" ({int(analysts)} anal.)" if analysts else ""
    if currency_prefix == "R$":
        display_value = f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        display_value = f"US$ {float(value):,.2f}"
    return f"{display_value}{analyst_text}", float(value)


def fetch_candidate_multiples(ticker, symbol, fallback=""):
    if CANDIDATE_IS_ETF.get(ticker):
        return complete_etf_multiples(fallback)
    if symbol.endswith(".SA"):
        return complete_candidate_multiples(fetch_b3_multiples(ticker), symbol, fallback)
    return complete_candidate_multiples(fetch_stockanalysis_multiples(ticker, fallback), symbol, fallback)


def complete_etf_multiples(fallback=""):
    values = {label: value for label, value in parse_candidate_multiples(fallback)}
    return (
        f"P/E {clean_display_multiple(values.get('P/E'), zero_as_na=True)} | "
        f"FWRD P/E {clean_display_multiple(values.get('FWRD P/E'), zero_as_na=True)} | "
        f"EV/EBITDA {clean_display_multiple(values.get('EV/EBITDA'), zero_as_na=True)} | "
        f"PEG Ratio {clean_display_multiple(values.get('PEG Ratio'), zero_as_na=True)}"
    )


def complete_candidate_multiples(multiples, symbol, fallback=""):
    values = {label: value for label, value in parse_candidate_multiples(multiples or fallback)}
    return complete_candidate_multiples_from_values(values)


def complete_candidate_multiples_from_values(values):
    return (
        f"P/E {clean_display_multiple(values.get('P/E'))} | "
        f"FWRD P/E {clean_display_multiple(values.get('FWRD P/E'))} | "
        f"EV/EBITDA {clean_display_multiple(values.get('EV/EBITDA'))} | "
        f"PEG Ratio {clean_display_multiple(values.get('PEG Ratio'), zero_as_na=True)}"
    )


def clean_display_multiple(value, zero_as_na=False):
    parsed = parse_multiple_value(value)
    if parsed is None:
        return "N/A" if zero_as_na else "0.00"
    if zero_as_na and abs(parsed) < 0.000001:
        return "N/A"
    if zero_as_na and 0 < parsed < 0.01:
        return "0.01"
    return f"{parsed:.2f}"


def fetch_b3_multiples(ticker):
    url = f"https://statusinvest.com.br/acoes/{ticker.lower()}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            page = response.read().decode("utf-8", errors="replace")
        clean = re.sub(r"\s+", " ", html.unescape(page))
        pe = extract_statusinvest_indicator(clean, "P/L")
        ev_ebitda = extract_statusinvest_indicator(clean, "EV/EBITDA")
        earnings_cagr = extract_statusinvest_indicator(clean, "CAGR Lucros 5 anos")
        revenue_cagr = extract_statusinvest_indicator(clean, "CAGR Receitas 5 anos")
    except Exception:
        pe = ev_ebitda = earnings_cagr = revenue_cagr = None
    pe_number = parse_ptbr_number(pe)
    growth_number = parse_ptbr_percent(earnings_cagr)
    if not growth_number or growth_number <= 0:
        growth_number = parse_ptbr_percent(revenue_cagr)
    if not growth_number or growth_number <= 0:
        growth_number = CANDIDATE_BUY_IN_DISCOUNT.get(ticker, 0.10)
    if pe_number is None:
        pe_number = 0
    fwrd_pe = format_multiple_number(pe_number / (1 + growth_number))
    peg = format_multiple_number(pe_number / (growth_number * 100))
    return (
        f"P/E {pe or format_multiple_number(pe_number)} | "
        f"FWRD P/E {fwrd_pe} | "
        f"EV/EBITDA {ev_ebitda or format_multiple_number(0)} | "
        f"PEG Ratio {peg}"
    )


def extract_statusinvest_indicator(clean_page, label):
    pattern = (
        rf'<h3 class="title[^"]*">{re.escape(label)}</h3>.*?'
        r'<strong class="value d-block lh-4 fs-4 fw-700">([^<]+)</strong>'
    )
    match = re.search(pattern, clean_page, re.I)
    return match.group(1).strip() if match else None


def fetch_stockanalysis_multiples(ticker, fallback=""):
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/statistics/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            page = response.read().decode("utf-8", errors="replace")
        clean = re.sub(r"\s+", " ", html.unescape(page))
    except Exception:
        return fallback
    pe = regex_first(clean, r"PE ratio is\s+([0-9.]+)")
    fwrd_pe = regex_first(clean, r"forward PE ratio is\s+([0-9.]+)")
    peg = regex_first(clean, r"PEG ratio is\s+([0-9.]+)")
    ev_ebitda = regex_first(clean, r"EV/EBITDA ratio is\s+([0-9.]+)")
    if multiple_missing_or_zero(peg):
        peg = fetch_finviz_peg(ticker)
    if multiple_missing_or_zero(peg):
        peg = calculate_stockanalysis_peg_ratio(ticker, pe, fwrd_pe)
    if not ev_ebitda:
        ev_ebitda = regex_first(clean, r"EV / EBITDA(?:(?!</tr>).)*title=\"([0-9.]+)\"")
    if not ev_ebitda:
        ev_ebitda = calculate_stockanalysis_ev_ebitda(ticker)
    return (
        f"P/E {pe or '0.00'} | "
        f"FWRD P/E {fwrd_pe or '0.00'} | "
        f"EV/EBITDA {ev_ebitda or '0.00'} | "
        f"PEG Ratio {peg or '0.00'}"
    )


def multiple_missing_or_zero(value):
    parsed = parse_multiple_value(value)
    return parsed is None or abs(parsed) < 0.000001


def fetch_finviz_peg(ticker):
    if ticker in FINVIZ_PEG_CACHE:
        return FINVIZ_PEG_CACHE[ticker]
    url = f"https://finviz.com/quote.ashx?t={urllib.parse.quote(ticker)}&p=d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    peg = None
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            page = response.read().decode("utf-8", errors="replace")
        match = re.search(r">PEG<.*?>([-0-9.]+)<", page, re.S)
        if match:
            value = match.group(1).strip()
            if value not in {"", "-", "0", "0.00"}:
                peg = value
    except Exception:
        peg = None
    FINVIZ_PEG_CACHE[ticker] = peg
    return peg


def calculate_stockanalysis_peg_ratio(ticker, pe, fwrd_pe):
    pe_value = parse_multiple_value(pe) or parse_multiple_value(fwrd_pe)
    growth_pct = fetch_stockanalysis_growth_rate(ticker)
    if pe_value is None or pe_value <= 0 or growth_pct is None or growth_pct <= 0:
        return None
    peg = pe_value / growth_pct
    if peg <= 0:
        return None
    return f"{max(peg, 0.01):.2f}"


def fetch_stockanalysis_growth_rate(ticker):
    if ticker in STOCKANALYSIS_GROWTH_CACHE:
        return STOCKANALYSIS_GROWTH_CACHE[ticker]
    clean = fetch_clean_page(f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/")
    if not clean:
        STOCKANALYSIS_GROWTH_CACHE[ticker] = None
        return None
    eps_values = extract_stockanalysis_growth_values(clean, "EPS Growth")
    revenue_values = extract_stockanalysis_growth_values(clean, "Revenue Growth")
    growth = select_growth_rate_for_peg(eps_values, revenue_values)
    STOCKANALYSIS_GROWTH_CACHE[ticker] = growth
    return growth


def extract_stockanalysis_growth_values(clean_page, label):
    index = clean_page.find(label)
    if index == -1:
        return []
    start = clean_page.rfind("<tr", 0, index)
    end = clean_page.find("</tr>", index)
    if start == -1 or end == -1:
        return []
    row = clean_page[start:end]
    values = []
    for token in re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?%", row):
        number = parse_us_percent(token)
        if number is not None:
            values.append(number)
    return values


def select_growth_rate_for_peg(eps_values, revenue_values):
    for values in (eps_values, revenue_values):
        window = values[-2:] if len(values) > 2 else values
        for value in window:
            if 3 <= value <= 80:
                return value
        for value in values:
            if 3 <= value <= 80:
                return value
    return None


def calculate_stockanalysis_ev_ebitda(ticker):
    ev = fetch_stockanalysis_enterprise_value(ticker)
    ebitda = fetch_stockanalysis_latest_ebitda(ticker)
    if ev is None or ebitda in (None, 0):
        return None
    return f"{ev / ebitda:.2f}"


def fetch_stockanalysis_enterprise_value(ticker):
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/statistics/"
    clean = fetch_clean_page(url)
    if not clean:
        return None
    match = re.search(r"enterprise value is\s+(-?\$?[0-9,.]+)\s+(billion|million)", clean, re.I)
    if not match:
        return None
    value = parse_us_number(match.group(1).replace("$", ""))
    if value is None:
        return None
    multiplier = 1000 if match.group(2).lower() == "billion" else 1
    return value * multiplier


def fetch_stockanalysis_latest_ebitda(ticker):
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/"
    clean = fetch_clean_page(url)
    if not clean:
        return None
    match = re.search(r"EBITDA.*?<td class=\"bolded[^\"]*\">([0-9,.-]+)</td>", clean, re.I)
    if not match:
        return None
    return parse_us_number(match.group(1))


def fetch_clean_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            page = response.read().decode("utf-8", errors="replace")
        return re.sub(r"\s+", " ", html.unescape(page))
    except Exception:
        return None


def regex_first(value, pattern):
    match = re.search(pattern, value or "", re.I)
    return clean_multiple_token(match.group(1)) if match else None


def clean_multiple_token(value):
    cleaned = (value or "").strip().rstrip(".")
    return cleaned if cleaned and cleaned.lower() != "n/a" else None


def parse_ptbr_number(value):
    if not value or value in {"-", "-%"}:
        return None
    cleaned = value.replace("%", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_us_number(value):
    cleaned = (value or "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_us_percent(value):
    cleaned = (value or "").replace("%", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_ptbr_percent(value):
    number = parse_ptbr_number(value)
    return number / 100 if number is not None else None


def format_multiple_number(value):
    if value is None:
        return "N/D"
    return f"{value:.2f}".replace(".", ",")


def fetch_b3_target_price(ticker):
    for forecast_ticker in (ticker, *B3_TARGET_ALIAS_TICKERS.get(ticker, ())):
        display, value = fetch_b3_tradingview_target_price(forecast_ticker)
        if value is None:
            continue
        if forecast_ticker != ticker:
            value = convert_b3_alias_target_to_ticker(ticker, forecast_ticker, value)
            if value is None:
                continue
            display = format_b3_target_display(value, extract_candidate_analyst_count(display))
        return display, value
    return CANDIDATE_TARGETS.get(ticker, "N/D"), None


def fetch_b3_tradingview_target_price(ticker):
    url = f"https://www.tradingview.com/symbols/BMFBOVESPA-{ticker}/forecast/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            page = response.read().decode("utf-8", errors="replace")
        clean = re.sub(r"\s+", " ", html.unescape(page.replace("<!-- -->", "")))
        if "Page not found" in clean:
            return CANDIDATE_TARGETS.get(ticker, "N/D"), None
        analysts = re.search(r"The\s+(\d+)\s+analysts offering 1-year price forecasts", clean, re.I)
        value = extract_b3_tradingview_average_target(clean)
        if value is None:
            value = extract_b3_tradingview_midpoint_target(clean)
        if value is None:
            return CANDIDATE_TARGETS.get(ticker, "N/D"), None
        display = format_b3_target_display(value, analysts.group(1) if analysts else None)
        return display, value
    except Exception:
        return CANDIDATE_TARGETS.get(ticker, "N/D"), None


def extract_b3_tradingview_average_target(clean):
    patterns = [
        r"price target is\s+([0-9,.]+)\s*BRL",
        r"average estimate of\s+([0-9,.]+)\s*BRL",
        r"average price target of\s+([0-9,.]+)\s*BRL",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean, re.I)
        if match:
            return parse_us_number(match.group(1))
    return None


def extract_b3_tradingview_midpoint_target(clean):
    match = re.search(
        r"max estimate of\s+([0-9,.]+)\s*BRL\s+and a min estimate of\s+([0-9,.]+)\s*BRL",
        clean,
        re.I,
    )
    if not match:
        return None
    high = parse_us_number(match.group(1))
    low = parse_us_number(match.group(2))
    if high is None or low is None or high <= 0 or low <= 0:
        return None
    return (high + low) / 2


def convert_b3_alias_target_to_ticker(ticker, forecast_ticker, target_value):
    ticker_price = fetch_latest_market_price(f"{ticker}.SA")
    forecast_price = fetch_latest_market_price(f"{forecast_ticker}.SA")
    if ticker_price is None or forecast_price in (None, 0):
        return None
    return target_value * (ticker_price / forecast_price)


def extract_candidate_analyst_count(display):
    match = re.search(r"(\d+)\s*anal", normalize_ws(str(display or "")), re.I)
    return match.group(1) if match else None


def format_b3_target_display(value, analysts=None):
    display = f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return display + (f" ({analysts} anal.)" if analysts else "")


def candidate_modeled_target_snapshot(item, current_price, consensus_target, multiples, price_context=None):
    if current_price is None or current_price <= 0:
        return {"target_value": None, "target_display": "N/D", "methods": {}}

    ticker = item.get("ticker", "")
    symbol = CANDIDATE_SYMBOLS.get(ticker, ticker)
    consensus_upside = candidate_upside_decimal(current_price, consensus_target)
    fundamentals = candidate_model_fundamentals(item, multiples, price_context or {})
    fallback_upside = candidate_fundamental_upside(fundamentals)
    methods = {
        "Goldman-style screener": candidate_screener_target(current_price, consensus_upside, fallback_upside, fundamentals),
        "Morgan Stanley-style DCF": candidate_dcf_target(current_price, consensus_upside, fallback_upside, fundamentals),
        "Bridgewater-style risk": candidate_risk_adjusted_target(current_price, consensus_upside, fallback_upside, fundamentals),
        "JPMorgan-style earnings": candidate_earnings_target(current_price, consensus_upside, fallback_upside, fundamentals),
        "BlackRock-style portfolio": candidate_portfolio_target(current_price, consensus_upside, fallback_upside, fundamentals),
    }
    values = [value for value in methods.values() if value is not None and value > 0]
    if not values:
        return {"target_value": None, "target_display": "N/D", "methods": methods}
    target_value = sum(values) / len(values)
    return {
        "target_value": target_value,
        "target_display": format_candidate_model_target_price(symbol, target_value),
        "methods": methods,
    }


def candidate_model_fundamentals(item, multiples, price_context):
    values = candidate_multiples_numeric(multiples)
    quality = clamp(item.get("quality", 50)) / 100
    ai_score = clamp(item.get("ai", 50)) / 100
    valuation = clamp(score_candidate_multiples(multiples)) / 100
    growth = candidate_growth_proxy(values, item)
    risk = candidate_model_risk_penalty(item, price_context, quality)
    moat = candidate_moat_score(item, quality, valuation)
    return {
        "valuation": valuation,
        "growth": growth,
        "risk": risk,
        "quality": quality,
        "ai": ai_score,
        "moat": moat,
        "is_etf": bool(item.get("etf")),
    }


def candidate_growth_proxy(values, item):
    pe = values.get("P/E")
    fwrd_pe = values.get("FWRD P/E")
    peg = values.get("PEG Ratio")
    quality = clamp(item.get("quality", 50)) / 100
    ai_score = clamp(item.get("ai", 50)) / 100
    growth = 0.10 + (quality - 0.50) * 0.10 + (ai_score - 0.50) * 0.08
    if pe and fwrd_pe and pe > 0 and fwrd_pe > 0:
        growth += clamp(pe / fwrd_pe - 1, -0.20, 0.60) * 0.22
    if peg and peg > 0:
        growth += clamp(1.25 - peg, -0.55, 0.95) * 0.10
    if item.get("turnaround"):
        growth += 0.08
    if item.get("cyclical"):
        growth += 0.04
    if item.get("etf"):
        growth = 0.08 + clamp(item.get("etf_value", 50)) / 100 * 0.14
    return clamp(growth, 0.02, 0.34)


def candidate_model_risk_penalty(item, price_context, quality):
    risk = 0.16 + max(0, 0.55 - quality) * 0.15
    volatility = (price_context or {}).get("volatility_20d")
    if volatility is not None:
        risk += clamp(volatility * 1.8, 0, 0.18)
    if item.get("china"):
        risk += 0.08
    if item.get("turnaround"):
        risk += 0.07
    if item.get("cyclical"):
        risk += 0.04
    if item.get("etf"):
        risk -= 0.03
    return clamp(risk, 0.08, 0.42)


def candidate_moat_score(item, quality, valuation):
    moat = quality * 0.65 + valuation * 0.20 + clamp(item.get("ai", 50)) / 100 * 0.15
    if item.get("turnaround"):
        moat -= 0.08
    if item.get("etf"):
        moat += 0.05
    return clamp(moat, 0.20, 0.92)


def candidate_fundamental_upside(fundamentals):
    if fundamentals.get("is_etf"):
        base = 0.20 + fundamentals["valuation"] * 0.28 + fundamentals["quality"] * 0.16 + fundamentals["ai"] * 0.12
    else:
        base = 0.18 + fundamentals["valuation"] * 0.45 + fundamentals["growth"] * 0.95 + fundamentals["moat"] * 0.18
    return clamp(base - fundamentals["risk"] * 0.45, 0.08, 1.25)


def blend_model_upside(consensus_upside, fallback_upside, consensus_weight):
    if consensus_upside is None:
        return fallback_upside
    return consensus_upside * consensus_weight + fallback_upside * (1 - consensus_weight)


def model_target_from_upside(current_price, upside):
    upside = clamp(upside, -0.20, 1.90)
    return current_price * (1 + upside)


def candidate_screener_target(current_price, consensus_upside, fallback_upside, fundamentals):
    upside = blend_model_upside(consensus_upside, fallback_upside, 0.40)
    upside += (fundamentals["valuation"] - 0.50) * 0.24
    upside += (fundamentals["moat"] - 0.50) * 0.12
    upside -= fundamentals["risk"] * 0.18
    return model_target_from_upside(current_price, upside)


def candidate_dcf_target(current_price, consensus_upside, fallback_upside, fundamentals):
    intrinsic_upside = fundamentals["growth"] * 2.15 + fundamentals["quality"] * 0.22 - fundamentals["risk"] * 0.50
    upside = blend_model_upside(consensus_upside, intrinsic_upside, 0.35)
    upside += (fundamentals["valuation"] - 0.50) * 0.10
    return model_target_from_upside(current_price, upside)


def candidate_risk_adjusted_target(current_price, consensus_upside, fallback_upside, fundamentals):
    upside = blend_model_upside(consensus_upside, fallback_upside, 0.50)
    risk_haircut = fundamentals["risk"] * (0.58 if fundamentals.get("is_etf") else 0.72)
    upside = upside * (1 - risk_haircut) + fundamentals["quality"] * 0.08
    return model_target_from_upside(current_price, upside)


def candidate_earnings_target(current_price, consensus_upside, fallback_upside, fundamentals):
    earnings_upside = fundamentals["growth"] * 1.75 + fundamentals["ai"] * 0.22 + fundamentals["valuation"] * 0.18
    earnings_upside -= fundamentals["risk"] * 0.24
    upside = blend_model_upside(consensus_upside, earnings_upside, 0.48)
    return model_target_from_upside(current_price, upside)


def candidate_portfolio_target(current_price, consensus_upside, fallback_upside, fundamentals):
    expected_return = fundamentals["quality"] * 0.24 + fundamentals["valuation"] * 0.20 + fundamentals["ai"] * 0.16
    expected_return += 0.10 if fundamentals.get("is_etf") else 0.04
    expected_return -= fundamentals["risk"] * 0.34
    upside = blend_model_upside(consensus_upside, expected_return, 0.32)
    return model_target_from_upside(current_price, upside)


def candidate_upside_decimal(current_price, target_price):
    pct = candidate_upside_pct(current_price, target_price)
    return pct / 100 if pct is not None else None


def format_candidate_model_target_price(symbol, value):
    if value is None:
        return "N/D"
    return format_candidate_stock_price(symbol, value)


def format_candidate_upside(current_price, target_price):
    upside = candidate_upside_pct(current_price, target_price)
    return format_signed_pct(upside) if upside is not None else "N/D"


def candidate_upside_pct(current_price, target_price):
    if current_price is None or target_price is None or current_price == 0:
        return None
    return (target_price / current_price - 1) * 100


def candidate_buy_in_value(ticker, current_price, target_price, price_context=None, multiples=None):
    if target_price is None:
        return None
    required_return = candidate_buy_in_required_return(ticker, multiples)
    return target_price / (1 + required_return)


def candidate_buy_in_required_return(ticker, multiples=None):
    minimum = max(CANDIDATE_REQUIRED_UPSIDE.get(ticker, 0.35), MIN_CANDIDATE_UPSIDE_PCT / 100)
    if CANDIDATE_IS_ETF.get(ticker):
        required = max(minimum + 0.18, 0.58)
    else:
        valuation_score = score_candidate_multiples(multiples or "")
        valuation_adjustment = (50 - valuation_score) / 100 * 0.22
        required = max(minimum + 0.28, 0.68) + valuation_adjustment
    risk_discount = CANDIDATE_BUY_IN_DISCOUNT.get(ticker, 0.09)
    required += max(0, risk_discount - 0.09) * 0.85
    return clamp(required, 0.55, 1.15)


def candidate_technical_buy_in_value(ticker, current_price, price_context):
    pullback = dynamic_pullback_pct(ticker, current_price, price_context)
    desired_ceiling = current_price * (1 - pullback)
    supports = candidate_support_levels(current_price, price_context)
    if not supports:
        return desired_ceiling

    near_supports = [value for value in supports if value <= desired_ceiling]
    if near_supports:
        return max(near_supports)

    nearest_support = max(supports)
    return min(nearest_support, desired_ceiling)


def candidate_support_levels(current_price, price_context):
    high_6m = price_context.get("high_6m")
    low_6m = price_context.get("low_6m")
    fib_38 = high_6m - ((high_6m - low_6m) * 0.382) if high_6m and low_6m and high_6m > low_6m else None
    fib_50 = high_6m - ((high_6m - low_6m) * 0.500) if high_6m and low_6m and high_6m > low_6m else None
    raw_levels = [
        price_context.get("low_20d") * 1.018 if price_context.get("low_20d") else None,
        price_context.get("low_50d") * 1.015 if price_context.get("low_50d") else None,
        price_context.get("sma_20d") * 0.990 if price_context.get("sma_20d") else None,
        price_context.get("sma_50d") * 0.985 if price_context.get("sma_50d") else None,
        price_context.get("sma_100d") * 0.980 if price_context.get("sma_100d") else None,
        price_context.get("percentile_35_6m") * 1.010 if price_context.get("percentile_35_6m") else None,
        price_context.get("percentile_25_6m") * 1.015 if price_context.get("percentile_25_6m") else None,
        fib_38,
        fib_50,
    ]
    levels = [
        value
        for value in raw_levels
        if value is not None and current_price * 0.55 <= value <= current_price * 0.997
    ]
    deduped = []
    for value in sorted(levels):
        if not deduped or abs(value / deduped[-1] - 1) > 0.004:
            deduped.append(value)
    return deduped


def dynamic_pullback_pct(ticker, current_price, price_context):
    volatility = price_context.get("volatility_20d")
    rank = price_context.get("percentile_rank_6m")
    base = 0.035
    if volatility is not None:
        base += min(max(volatility * 1.35, 0), 0.085)
    else:
        base += 0.025
    if rank is not None:
        base += max(0, rank - 0.55) * 0.055
        base -= max(0, 0.35 - rank) * 0.020
    risk_discount = CANDIDATE_BUY_IN_DISCOUNT.get(ticker, 0.09)
    base += max(0, risk_discount - 0.09) * 0.30
    return clamp(base, 0.025, 0.18)


def format_candidate_buy_in(ticker, current_price, target_price=None, price_context=None, multiples=None):
    price, analysis = format_candidate_buy_in_parts(ticker, current_price, target_price, price_context, multiples)
    return f"{price} | {analysis}"


def format_candidate_buy_in_parts(ticker, current_price, target_price=None, price_context=None, multiples=None):
    analysis = CANDIDATE_BUY_IN_ANALYSIS.get(ticker, "AI: aguardar melhor margem de seguranca.")
    buy_price = candidate_buy_in_value(ticker, current_price, target_price, price_context, multiples)
    if buy_price is None:
        return "N/D", analysis
    symbol = CANDIDATE_SYMBOLS.get(ticker, ticker)
    price = format_candidate_stock_price(symbol, buy_price)
    return price, analysis


def format_candidate_price_to_buy_in(ticker, current_price, target_price=None, price_context=None, multiples=None):
    if current_price is None:
        return "N/D"
    buy_price = candidate_buy_in_value(ticker, current_price, target_price, price_context, multiples)
    distance = candidate_buy_in_distance_pct(current_price, buy_price)
    return format_signed_pct(distance) if distance is not None else "N/D"


def parse_candidate_multiples(multiples):
    ordered = {
        "P/E": "0.00",
        "FWRD P/E": "0.00",
        "EV/EBITDA": "0.00",
        "PEG Ratio": "0.00",
    }
    for raw_part in (multiples or "").split("|"):
        part = normalize_ws(raw_part)
        if not part:
            continue
        label = None
        value = None
        for candidate in ("EV/EBITDA", "Forward P/E", "FWRD P/E", "Fwrd P/E", "Fwd P/E", "PEG Ratio", "PEG", "P/E"):
            if part.lower().startswith(candidate.lower()):
                label = candidate
                value = normalize_ws(part[len(candidate):]) or "N/D"
                break
        if not label:
            continue
        if label in {"Forward P/E", "FWRD P/E", "Fwrd P/E", "Fwd P/E"}:
            label = "FWRD P/E"
        elif label == "PEG":
            label = "PEG Ratio"
        ordered[label] = value or "0.00"
    return list(ordered.items())


def render_candidate_multiples_html(multiples):
    lines = []
    for label, value in parse_candidate_multiples(multiples):
        lines.append(
            "<div class='multiple-line'>"
            f"<span class='multiple-label'>{html.escape(label)}</span>"
            f"<span class='multiple-value'>{html.escape(value)}</span>"
            "</div>"
        )
    return "<div class='multiple-lines'>" + "".join(lines) + "</div>"


def split_candidate_target_display(target):
    target = normalize_ws(target)
    if not target or target == "N/D":
        return "N/D", ""
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", target)
    if not match:
        return target, ""
    value = normalize_ws(match.group(1))
    analysts = normalize_ws(match.group(2)).replace("anal.", "analistas")
    analysts = re.sub(r"\banal\b", "analistas", analysts)
    return value, analysts


def render_candidate_target_html(consensus, upside, model_target=None):
    value, analysts = split_candidate_target_display(consensus)
    analyst_line = (
        f"<span class='target-analysts'>({html.escape(analysts)})</span>"
        if analysts
        else ""
    )
    model_target = model_target or "N/D"
    return (
        "<span class='target-model-label'>Consensus</span>"
        f"<span class='target-price'>{html.escape(value)}</span>"
        f"{analyst_line}"
        "<span class='target-model-label target-model-label-tp'>Our TP</span>"
        f"<span class='model-target-price'>{html.escape(model_target)}</span>"
        "<span class='target-upside-label'>Upside</span>"
        f"<span class='target-upside-value'>{html.escape(upside)}</span>"
    )


def format_candidate_multiples_text(multiples):
    return "; ".join(
        f"{label} {value}"
        for label, value in parse_candidate_multiples(multiples)
    )


def candidate_buy_in_distance_pct(current_price, buy_price):
    if current_price is None or buy_price is None or buy_price == 0:
        return None
    return (current_price / buy_price - 1) * 100


def format_candidate_stock_price(symbol, value):
    if value is None:
        return "N/D"
    if symbol.endswith(".SA"):
        return f"R$ {value:,.2f}"
    return f"US$ {value:,.2f}"


def ensure_folder_path(password, names):
    parent = {"distinguished": "inbox"}
    folder_id = None
    for name in names:
        found = find_child_folder(password, parent, name)
        if not found:
            found = create_child_folder(password, parent, name)
        folder_id = found
        parent = {"id": folder_id["id"], "change_key": folder_id.get("change_key", "")}
    return folder_id


def find_child_folder(password, parent, display_name):
    parent_xml = folder_parent_xml(parent)
    body = f"""
<m:FindFolder Traversal="Shallow">
  <m:FolderShape>
    <t:BaseShape>Default</t:BaseShape>
  </m:FolderShape>
  <m:ParentFolderIds>{parent_xml}</m:ParentFolderIds>
</m:FindFolder>"""
    root = ET.fromstring(ews_request(password, body))
    for folder in root.findall(".//t:Folder", NS):
        if text(folder, "t:DisplayName") == display_name:
            folder_id = folder.find("t:FolderId", NS)
            if folder_id is not None:
                return {"id": folder_id.attrib.get("Id", ""), "change_key": folder_id.attrib.get("ChangeKey", "")}
    return None


def create_child_folder(password, parent, display_name):
    parent_xml = folder_parent_xml(parent)
    body = f"""
<m:CreateFolder>
  <m:ParentFolderId>{parent_xml}</m:ParentFolderId>
  <m:Folders>
    <t:Folder>
      <t:DisplayName>{html.escape(display_name)}</t:DisplayName>
    </t:Folder>
  </m:Folders>
</m:CreateFolder>"""
    root = ET.fromstring(ews_request(password, body))
    response = root.find(".//m:CreateFolderResponseMessage", NS)
    if response is None or response.attrib.get("ResponseClass") != "Success":
        code = text(root, ".//m:ResponseCode", "unknown")
        message = text(root, ".//m:MessageText", "")
        raise RuntimeError(f"CreateFolder failed for {display_name}: {code} {message}")
    folder_id = root.find(".//t:FolderId", NS)
    if folder_id is None:
        raise RuntimeError(f"CreateFolder failed for {display_name}: no FolderId returned")
    return {"id": folder_id.attrib.get("Id", ""), "change_key": folder_id.attrib.get("ChangeKey", "")}


def folder_parent_xml(parent):
    if parent.get("distinguished"):
        return f'<t:DistinguishedFolderId Id="{html.escape(parent["distinguished"])}" />'
    change_key = parent.get("change_key")
    change_attr = f' ChangeKey="{html.escape(change_key)}"' if change_key else ""
    return f'<t:FolderId Id="{html.escape(parent["id"])}"{change_attr} />'


def ensure_operational_folders(password):
    root = ["Chief of Staff Digital"]
    folder_names = [
        "Quarentena - Spam Provavel",
        "01 Responder",
        "02 A Fazer",
        "03 Aguardando",
        "04 Alta Atencao",
        "Arquivo - Investimentos",
        "Arquivo - Documentos",
        "Arquivo - Bancos",
        "Arquivo - Juridico",
        "Arquivo - Barcos",
        "Arquivo - Casa e Obras",
        "Arquivo - Empresas",
        "Arquivo - Viagens",
        "Arquivo - Fornecedores",
        "Newsletters",
    ]
    created_or_found = {}
    for name in folder_names:
        created_or_found[name] = ensure_folder_path(password, root + [name])
    return created_or_found


def move_items_to_folder(password, messages, folder_id):
    movable = [msg for msg in messages if msg.get("item_id")]
    if not movable:
        return 0
    item_ids = "\n".join(
        f'<t:ItemId Id="{html.escape(msg["item_id"])}"'
        + (f' ChangeKey="{html.escape(msg["change_key"])}"' if msg.get("change_key") else "")
        + " />"
        for msg in movable
    )
    body = f"""
<m:MoveItem>
  <m:ToFolderId>
    <t:FolderId Id="{html.escape(folder_id['id'])}" />
  </m:ToFolderId>
  <m:ItemIds>
    {item_ids}
  </m:ItemIds>
</m:MoveItem>"""
    root = ET.fromstring(ews_request(password, body))
    moved = 0
    errors = []
    for response in root.findall(".//m:MoveItemResponseMessage", NS):
        if response.attrib.get("ResponseClass") == "Success":
            moved += 1
        else:
            errors.append(f"{text(response, 'm:ResponseCode', 'unknown')} {text(response, 'm:MessageText', '')}".strip())
    if errors:
        print("Move warnings:", "; ".join(errors[:3]))
    return moved


def write_audit_csv(path, emails):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "classification",
                "reason",
                "received",
                "sender",
                "sender_email",
                "subject",
                "is_read",
                "target_folder",
            ],
        )
        writer.writeheader()
        for msg in emails:
            writer.writerow(
                {
                    "classification": msg.get("classification", ""),
                    "reason": msg.get("classification_reason", ""),
                    "received": msg["received"].isoformat() if msg.get("received") else "",
                    "sender": msg.get("sender", ""),
                    "sender_email": msg.get("sender_email", ""),
                    "subject": msg.get("subject", ""),
                    "is_read": msg.get("is_read", ""),
                    "target_folder": msg.get("target_folder", ""),
                }
            )


def route_archive_folder(msg):
    blob = f"{msg.get('sender','')} {msg.get('sender_email','')} {msg.get('subject','')} {msg.get('body','')[:500]}".lower()
    if any(term in blob for term in ["perfeita", "boat", "boats", "billfish", "top fly", "shaft", "tach", "vetus", "bow thruster", "marina"]):
        return "Arquivo - Barcos"
    if any(term in blob for term in ["evc", "obra", "residencia", "residência", "figueira", "paisagismo", "vistoria", "home network", "automacao", "automação", "audio", "video", "iot"]):
        return "Arquivo - Casa e Obras"
    if any(term in blob for term in ["btg", "billfish fia", "fundo", "dividendos", "carteira", "azapice", "trident", "trust", "bvi", "capital & properties"]):
        return "Arquivo - Investimentos"
    if any(term in blob for term in ["citi", "picpay", "telefonica", "extrato", "aadvantage", "banco", "bank"]):
        return "Arquivo - Bancos"
    if any(term in blob for term in ["inventário", "inventario", "espólio", "espolio", "procuração", "procuracao", "adv", "legal", "campbellslegal", "bradesco", "divorcio", "divórcio"]):
        return "Arquivo - Juridico"
    if any(term in blob for term in ["marriott", "reserva", "reservation", "rent a car", "aluguel de veículos", "aluguel de veiculos"]):
        return "Arquivo - Viagens"
    if any(term in blob for term in ["nota fiscal", "certidão", "certidao", "documentos", "relatório", "relatorio", "planilha", "signed", "fotos", "laudo"]):
        return "Arquivo - Documentos"
    if any(term in blob for term in ["oakberry", "nannacay", "nova bvi", "empresa", "proposta", "orçamento", "orcamento"]):
        return "Arquivo - Empresas"
    return "Arquivo - Fornecedores"


NEWSLETTER_ROUTE_TERMS = [
    "newsletter",
    "news letter",
    "digest",
    "boletim",
    "leia mais",
    "read more",
    "view this email in your browser",
    "view in browser",
    "manage preferences",
    "email preferences",
    "unsubscribe",
    "descadastrar",
    "webinar",
    "masterclass",
    "morning call",
    "weekly update",
    "monthly update",
    "roundup",
    "research",
    "by mckinsey",
    "via brazil journal",
]

TASK_ROUTE_TERMS = [
    "docusign",
    "assinar",
    "assinatura",
    "execute",
    "preencher",
    "formulário",
    "formulario",
    "aprovar",
    "approve",
    "enviar documento",
    "send document",
    "payment due",
    "pagar",
    "pagamento pendente",
    "vencimento",
    "invoice due",
    "wire transfer",
    "transferência",
    "transferencia",
]

WAITING_ROUTE_TERMS = [
    "assim que analisar",
    "assim que eu analisar",
    "tão logo",
    "tao logo",
    "retorno pra você",
    "retorno para você",
    "retorno pra voces",
    "retorno para voces",
    "em análise",
    "em analise",
    "estamos analisando",
    "under review",
    "we will get back",
]


def route_blob(msg):
    return f"{msg.get('sender','')} {msg.get('sender_email','')} {msg.get('subject','')} {msg.get('body','')[:1200]}".lower()


def is_newsletter_like(msg):
    blob = route_blob(msg)
    return any(term in blob for term in NEWSLETTER_ROUTE_TERMS)


def is_task_like(msg):
    blob = route_blob(msg)
    return any(term in blob for term in TASK_ROUTE_TERMS)


def is_waiting_like(msg):
    blob = route_blob(msg)
    return any(term in blob for term in WAITING_ROUTE_TERMS)


def route_email_folder(msg, include_informative=True):
    classification = msg.get("classification", "")
    if classification == "Quarentena sugerida":
        return "Newsletters" if is_newsletter_like(msg) else "Quarentena - Spam Provavel"
    if classification == "Responder / revisar":
        return "02 A Fazer" if is_task_like(msg) else "01 Responder"
    if classification == "Alta atencao":
        return "02 A Fazer" if is_task_like(msg) else "04 Alta Atencao"
    if classification == "Arquivar / informativo":
        if not include_informative:
            return None
        if is_waiting_like(msg):
            return "03 Aguardando"
        if is_newsletter_like(msg):
            return "Newsletters"
        return route_archive_folder(msg)
    return None


def organize_classified_items(password, emails, folders, include_informative=True):
    grouped = {}
    for msg in emails:
        folder_name = route_email_folder(msg, include_informative=include_informative)
        msg["target_folder"] = folder_name or ""
        if not folder_name:
            continue
        grouped.setdefault(folder_name, []).append(msg)

    moved = {}
    for folder_name, messages in grouped.items():
        folder = folders.get(folder_name)
        if folder:
            moved[folder_name] = move_items_to_folder(password, messages, folder)
    return moved


def load_whatsapp_items(path):
    if not path:
        return []
    source = Path(path)
    if not source.exists():
        return []
    items = json.loads(source.read_text(encoding="utf-8"))
    normalized = []
    for item in items:
        message = normalize_ws(item.get("preview", ""))
        normalized.append(
            {
                "contact": item.get("contact", "(sem contato)"),
                "time": item.get("time", ""),
                "unread_count": item.get("unread_count", 1),
                "preview": message,
                "priority": classify_whatsapp_priority(item.get("contact", ""), message),
                "summary": summarize_whatsapp(item.get("contact", ""), message),
                "reply": suggest_whatsapp_reply(item.get("contact", ""), message),
            }
        )
    return normalized


def count_whatsapp_unread_messages(whatsapp_items):
    total = 0
    for item in whatsapp_items:
        try:
            total += int(item.get("unread_count") or 1)
        except (TypeError, ValueError):
            total += 1
    return total


def read_json_file(path):
    try:
        source = Path(path)
        if source.exists():
            return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def format_status_time(value):
    if not value:
        return "nao disponivel"
    try:
        parsed = dt.datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TIMEZONE)
        return parsed.astimezone(TIMEZONE).strftime("%d/%m %H:%M")
    except ValueError:
        return str(value)


def file_mtime_status(path):
    source = Path(path)
    if not source.exists():
        return "nao disponivel"
    modified = dt.datetime.fromtimestamp(source.stat().st_mtime, TIMEZONE)
    return modified.strftime("%d/%m %H:%M")


def whatsapp_health_label(whatsapp_items):
    status = read_json_file(OUT_DIR / "whatsapp-status.json")
    if status.get("status") == "ok" and status.get("logged_in"):
        messages = status.get("unread_messages")
        suffix = f" - {messages} msg" if messages is not None else ""
        return f"ok/logado{suffix}"
    if status:
        return f"atencao - {status.get('status', 'sem status')}"
    if whatsapp_items:
        return f"json ok - {count_whatsapp_unread_messages(whatsapp_items)} msg"
    return "ok/logado - sem nao lidas"


def build_automation_health(emails, whatsapp_items, billfish, pluggy=None, pdf_delivery_status="sim"):
    email_label = f"ok - {len(emails)} analisados"
    billfish_label = "fonte encontrada" if billfish.get("available") else "indisponivel"
    latest = billfish.get("latest") or {}
    if billfish.get("available") and latest.get("date"):
        billfish_label = f"fonte encontrada - {latest.get('date')}"
    pluggy_label = "ok" if (pluggy or {}).get("available") else "nao configurado"
    if (pluggy or {}).get("configured") and not (pluggy or {}).get("available"):
        pluggy_label = "sem dados"
    return [
        {"label": "Email", "value": email_label},
        {"label": "WhatsApp", "value": whatsapp_health_label(whatsapp_items)},
        {"label": "Billfish BTG", "value": billfish_label},
        {"label": "Open Finance", "value": pluggy_label},
        {"label": "AWS cron", "value": f"ultima execucao {file_mtime_status(OUT_DIR / 'cron.log')}"},
        {"label": "PDF enviado", "value": pdf_delivery_status},
    ]


def classify_whatsapp_priority(contact, message):
    blob = f"{contact} {message}".lower()
    if any(term in blob for term in ["banco", "cartão", "cartao", "pix", "compra", "fraude", "urgente", "contrato", "documento"]):
        return "Alta atencao"
    if any(term in blob for term in ["me liga", "retoma", "semana", "querendo", "procurando", "apartamento", "brickell"]):
        return "Responder"
    return "Revisar"


def summarize_whatsapp(contact, message):
    if not message:
        return "Mensagem sem preview disponivel."
    if len(message) <= 180:
        return message
    return message[:177].rstrip() + "..."


def suggest_whatsapp_reply(contact, message):
    blob = message.lower()
    if "brickell" in blob or "apartamento" in blob:
        return "Oi Vivianne, obrigado pelo contato. Estou olhando algumas opções em Brickell. Te mando com mais calma o perfil do que estou buscando e podemos falar."
    if "começo da semana" in blob or "retoma" in blob:
        return "Fala Caio, obrigado pela mensagem. Vamos nos falar no começo da semana sim. Bom fim de semana para você também."
    if len(message) <= 40:
        return "Responder de forma contextual depois de abrir a conversa."
    return "Obrigado pela mensagem. Vou ver isso com calma e te retorno."


def parse_ews_time(value):
    if not value:
        return None
    value = value.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(value).astimezone(TIMEZONE)
    except ValueError:
        return None


def normalize_ws(value):
    return re.sub(r"\s+", " ", value or "").strip()


def classify_email(msg):
    blob = f"{msg['sender']} {msg['sender_email']} {msg['subject']} {msg['body'][:500]}".lower()
    sender = (msg["sender_email"] or msg["sender"] or "").lower()
    subject = (msg["subject"] or "").lower()
    high_attention = [
        "wire",
        "transfer",
        "swift",
        "aba",
        "bank",
        "banco",
        "docusign",
        "agreement",
        "contrato",
        "assinatura",
        "liability",
        "remessa",
        "certidao",
        "certidão",
        "fundo",
        "carteira",
        "dividendos",
        "invoice",
        "payment",
        "pagamento",
        "comprovante",
        "receipt",
        "tax",
        "imposto",
        "lawyer",
        "attorney",
        "advogado",
        "court",
        "processo",
        "cartório",
        "cartorio",
        "insurance",
        "seguro",
        "policy",
        "apólice",
        "apolice",
    ]
    strong_spam = [
        "unsubscribe",
        "opt out",
        "opt-out",
        "manage preferences",
        "email preferences",
        "view this email in your browser",
        "view in browser",
        "descadastrar",
        "descadastro",
        "cancelar inscrição",
        "cancelar inscricao",
        "remover inscrição",
        "remover inscricao",
        "não quero receber",
        "nao quero receber",
    ]
    marketing_terms = [
        "marketing",
        "mailchimp",
        "hubspot",
        "sendgrid",
        "eventbrite",
        "sympla",
        "newsletter",
        "news letter",
        "promo",
        "promocao",
        "promoção",
        "oferta",
        "desconto",
        "sale",
        "black friday",
        "cyber monday",
        "webinar",
        "masterclass",
        "evento online",
        "convite para",
        "inscreva-se",
        "register now",
        "baixe agora",
        "download now",
        "whitepaper",
        "ebook",
        "leia mais",
        "read more",
        "clique aqui",
        "click here",
        "relatorio da carteira diaria",
        "relatório da carteira diária",
        "daily report",
        "digest",
        "boletim",
        "comunicado ao mercado",
        "research",
        "morning call",
        "weekly update",
        "monthly update",
        "roundup",
        "tendências",
        "tendencias",
        "insights",
        "conteúdo",
        "conteudo",
        "conteudos",
        "conteúdos",
        "live:",
        "ao vivo",
        "última chance",
        "ultima chance",
        "last chance",
        "save the date",
        "new listings",
        "top viewed",
        "most viewed",
        "price drops",
        "new arrivals",
        "cashback",
        "expires",
        "rewards expires",
        "% off",
        " off ",
        "sale",
        "black out",
        "catch up",
        "top videos",
        "stock jumps",
        "strong buy",
        "summer",
        "you might like",
        "performance",
        "gear feeling",
        "bônus",
        "bonus",
        "tv nova",
        "torcida",
        "lua nova",
        "standout shows",
        "behind the bricks",
        "go-kart",
        "medical kits",
        "on business",
        "by mckinsey",
        "via brazil journal",
        "welcome to",
    ]
    automated_sender_terms = [
        "no-reply",
        "noreply",
        "do-not-reply",
        "donotreply",
        "notification",
        "notifications",
        "notificacoes",
        "notificações",
        "comunicacao",
        "comunicação",
        "news",
        "mailer",
        "mailing",
        "mkt",
        "marketing",
        "robot",
        "automated",
        "alert",
        "alerts",
    ]
    bulk_sender_patterns = [
        "consumer@e.mail.realtor.com",
        "store-news@amazon.com",
        "contato@doutornature.com",
        "response.cnbc.com",
        "tipranks.com",
        "e-mail.gopro.com",
        "novidade.casasbahia.com.br",
        "tackledirect.com",
        "members.netflix.com",
        "meltontackle.com",
        "stealstock.com",
        "universalstudioshollywood.com",
        "notify.bonifiq.com.br",
        "curadoria.fastshop.com.br",
        "mail.ralphlauren.com",
        "news@blplegal.com",
        "e.lululemon.com",
        "g.shopifyemail.com",
        "mx.thelotter.net",
        "mail.yeti.com",
        "email.sorteonline.com.br",
        "comunicado.smiles.com.br",
        "vestaboard.com",
        "viavini.com.br",
        "citimarinestore.com",
        "e.drogaraia.com.br",
        "novidades.riachuelo.com.br",
        "worldsurfleague.com",
        "shared1.ccsend.com",
        "mkt.tf.com.br",
        "mail.nelogica.com.br",
        "guiasaudenatural.com",
        "personare.com.br",
        "mercadolivre.com.br",
        "insideapple.apple.com",
        "brickyard.com",
        "from.k1speed.com",
        "braziljournal.com",
        "fisheriessupply.com",
        "mn.co",
    ]
    obvious_thread_terms = [
        "re:",
        "fw:",
        "fwd:",
        "res:",
    ]
    replyish = [
        "please",
        "could you",
        "por favor",
        "favor",
        "aguardo",
        "retorno",
        "question",
        "dúvida",
        "duvida",
        "asap",
        "checking in",
        "pending information",
        "requires your attention",
        "action required",
    ]

    if any(term in blob for term in high_attention):
        msg["classification_reason"] = "Protegido: financeiro/juridico/contrato/documento sensivel."
        return "Alta atencao"

    score = 0
    reasons = []
    for term in strong_spam:
        if term in blob:
            score += 4
            reasons.append(term)
    for term in marketing_terms:
        if term in blob:
            score += 2
            reasons.append(term)
    for term in automated_sender_terms:
        if term in sender:
            score += 2
            reasons.append(f"sender:{term}")
    for pattern in bulk_sender_patterns:
        if pattern in sender:
            score += 5
            reasons.append(f"bulk:{pattern}")

    if any(subject.startswith(term) for term in obvious_thread_terms):
        score -= 2
    if "?" in msg["subject"] or any(term in blob for term in replyish):
        score -= 1

    if score >= 4:
        msg["classification_reason"] = "Quarentena por sinais: " + ", ".join(reasons[:6])
        return "Quarentena sugerida"
    if any(term in blob for term in replyish):
        msg["classification_reason"] = "Pede retorno ou acao."
        return "Responder / revisar"
    if not msg["is_read"] and not any(term in sender for term in automated_sender_terms):
        msg["classification_reason"] = "Nao lido de remetente nao automatico."
        return "Responder / revisar"
    msg["classification_reason"] = "Sem pedido claro de acao."
    return "Arquivar / informativo"


def summarize_email(msg):
    body = msg["body"]
    if not body:
        return "Sem corpo de mensagem disponivel."
    sentences = re.split(r"(?<=[.!?])\s+", body)
    summary = " ".join(sentences[:2])[:420]
    return summary or body[:420]


def suggested_reply(msg, classification):
    if classification == "Quarentena sugerida":
        return "Nenhuma resposta."
    if classification == "Arquivar / informativo":
        return "Obrigado pelo envio. Recebido. Abs., Eduardo"
    if classification == "Alta atencao":
        return (
            "Obrigado pelo envio. Vou conferir as informacoes com calma antes de avançar "
            "e retorno caso precise de algum ajuste ou confirmacao. Abs., Eduardo"
        )
    return (
        "Obrigado pela mensagem. Vou verificar esse ponto e retorno em seguida. "
        "Abs., Eduardo"
    )


def clip_action_text(value, limit=170):
    value = normalize_ws(str(value or ""))
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def clean_action_subject(subject):
    subject = normalize_ws(subject or "(sem assunto)")
    subject = re.sub(r"^(re|fw|fwd|enc):\s*", "", subject, flags=re.I)
    return clip_action_text(subject, 62)


def action_blob(msg):
    return f"{msg.get('sender','')} {msg.get('sender_email','')} {msg.get('subject','')} {msg.get('body','')[:1400]}".lower()


def infer_action_step(msg):
    blob = action_blob(msg)
    if any(term in blob for term in ["docusign", "assinar", "assinatura", "execute the contract"]):
        return "Conferir nomes, valores e responsabilidades; assinar apenas se os pontos estiverem corretos."
    if any(term in blob for term in ["wire", "swift", "aba", "remessa", "beneficiary", "beneficiario", "transfer"]):
        return "Validar beneficiario, conta e banco antes de executar cambio/remessa."
    if any(term in blob for term in ["formulario", "formulário", "risk", "seguro", "prestamista", "insurance"]):
        return "Definir responsavel pelo preenchimento e enviar dados faltantes."
    if any(term in blob for term in ["cartao", "cartão", "credit card", "address", "endereco", "endereço"]):
        return "Confirmar criterio exigido e responder com os dados que atendem a regra."
    if any(term in blob for term in ["contrato", "agreement", "liability", "addendum"]):
        return "Revisar obrigações, responsabilidade futura e pontos comerciais antes de aprovar."
    if any(term in blob for term in ["certidao", "certidão", "documento", "anexo"]):
        return "Baixar, arquivar e encaminhar o documento se houver destinatario."
    return "Definir se responde, delega ou agenda um bloco curto para resolver."


def action_context(msg):
    sender = clip_action_text(msg.get("sender") or msg.get("sender_email") or "Remetente nao identificado", 42)
    summary = clip_action_text(msg.get("summary") or msg.get("body") or msg.get("subject"), 150)
    return f"{sender}: {summary}"


def build_decision_queue(emails):
    important = [msg for msg in emails if msg.get("classification") in {"Alta atencao", "Responder / revisar"}]
    decision_terms = [
        "docusign", "assinar", "assinatura", "aprovar", "approve", "contrato", "agreement",
        "wire", "swift", "aba", "remessa", "transfer", "cartao", "cartão", "credit card",
        "formulario", "formulário", "seguro", "prestamista", "certidao", "certidão",
    ]

    def score(msg):
        blob = action_blob(msg)
        return sum(2 for term in decision_terms if term in blob) + (2 if msg.get("classification") == "Alta atencao" else 0)

    rows = []
    for msg in sorted(important, key=score, reverse=True):
        if score(msg) <= 0 and len(rows) >= 1:
            continue
        rows.append(
            {
                "decision": clean_action_subject(msg.get("subject")),
                "context": action_context(msg),
                "action": infer_action_step(msg),
            }
        )
        if len(rows) == 3:
            break
    return rows


def followup_age_text(received, day):
    if not received:
        return "Data nao disponivel"
    day_date = day.date() if hasattr(day, "date") else day
    received_date = received.date() if hasattr(received, "date") else received
    age_days = max(0, (day_date - received_date).days)
    if age_days == 0:
        return "Recebido hoje"
    if age_days == 1:
        return "Aberto ha 1 dia"
    return f"Aberto ha {age_days} dias"


def build_followups(emails, day):
    candidates = [
        msg for msg in emails
        if msg.get("classification") in {"Alta atencao", "Responder / revisar"} or is_waiting_like(msg)
    ]
    candidates = sorted(
        candidates,
        key=lambda msg: (
            0 if is_waiting_like(msg) else 1,
            msg.get("received") or dt.datetime.max.replace(tzinfo=TIMEZONE),
        ),
    )
    rows = []
    seen = set()
    for msg in candidates:
        subject = clean_action_subject(msg.get("subject"))
        if subject.lower() in seen:
            continue
        seen.add(subject.lower())
        if is_waiting_like(msg):
            status = "Aguardando retorno"
        elif msg.get("classification") == "Alta atencao":
            status = "Alta atencao"
        else:
            status = "Pede resposta"
        rows.append(
            {
                "subject": subject,
                "status": f"{status} - {followup_age_text(msg.get('received'), day)}",
                "next": infer_action_step(msg),
            }
        )
        if len(rows) == 3:
            break
    return rows


def infer_agenda_prep(event):
    blob = f"{event.get('subject','')} {event.get('location','')}".lower()
    if any(term in blob for term in ["justin", "lav", "fly", "boat", "barco"]):
        return "Levar dúvidas sobre responsabilidades, saldo minimo, operação e próximos passos."
    if any(term in blob for term in ["banco", "citi", "btg", "efg", "invest", "fundo"]):
        return "Separar dados financeiros, pendências e decisões que precisam sair da conversa."
    if any(term in blob for term in ["adv", "legal", "contrato", "agreement", "juridico", "jurídico"]):
        return "Revisar documentos, riscos e pontos que exigem aprovação antes da reunião."
    if any(term in blob for term in ["obra", "casa", "apartamento", "brickell", "imovel", "imóvel"]):
        return "Definir objetivo, orçamento, restrições e decisões esperadas."
    return "Entrar com objetivo claro, contexto anterior e próxima ação desejada."


def build_agenda_brief(events):
    rows = []
    for event in events[:3]:
        if event.get("all_day"):
            when = "Dia inteiro"
        elif event.get("start") and event.get("end"):
            when = f"{event['start'].strftime('%H:%M')} - {event['end'].strftime('%H:%M')}"
        elif event.get("start"):
            when = event["start"].strftime("%H:%M")
        else:
            when = "Horario nao disponivel"
        context = event.get("location") or when
        rows.append(
            {
                "meeting": clip_action_text(event.get("subject") or "(sem titulo)", 62),
                "context": clip_action_text(context, 90),
                "prep": infer_agenda_prep(event),
            }
        )
    return rows


def render_html(day, events, emails, markets, whatsapp_items, billfish, forecast=None, news=None, candidate_data=None, report_title="Morning Summary", automation_health=None, world_cup=None, brokerage_notes=None, pluggy=None):
    important = [e for e in emails if e["classification"] != "Quarentena sugerida"][:15]
    quarantine = [e for e in emails if e["classification"] == "Quarentena sugerida"][:10]
    high = [e for e in important if e["classification"] == "Alta atencao"]
    reply = [e for e in important if e["classification"] == "Responder / revisar"]
    priorities = build_priorities(events, important)
    generated = dt.datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M")
    whatsapp_unread_messages = count_whatsapp_unread_messages(whatsapp_items)

    stats = [
        ("Agenda", str(len(events)), "compromissos hoje"),
        ("WhatsApp", str(whatsapp_unread_messages), "mensagens nao lidas"),
        ("Alta atencao", str(len(high)), "emails sensiveis"),
        ("Responder", str(len(reply)), "pedem retorno"),
        ("Quarentena", str(len(quarantine)), "itens filtrados"),
    ]
    stat_cards = "\n".join(
        f"<div class='stat'><div class='stat-label'>{html.escape(label)}</div><div class='stat-value'>{value}</div><div class='stat-note'>{html.escape(note)}</div></div>"
        for label, value, note in stats
    )
    market_sections = render_market_sections_html(markets)
    pluggy_panel = render_pluggy_panel_html(pluggy or {})
    pluggy_statements_panel = render_pluggy_recent_statements_html(pluggy or {}, days=2)
    billfish_panel = render_billfish_panel_html(billfish)
    brokerage_panel = render_brokerage_notes_panel_html(brokerage_notes or {})
    candidate_b3_panel = render_cheap_stocks_html(candidate_data or {}, groups=("B3",), compact=True)
    candidate_us_panel = render_cheap_stocks_html(candidate_data or {}, groups=("Nasdaq", "NYSE"), compact=True)
    brokerage_trade_count = len((brokerage_notes or {}).get("trades") or [])
    brokerage_summary_count = len((brokerage_notes or {}).get("financial_summary") or [])
    candidate_b3_intro = (
        '<div class="section-title candidate-stocks-title">Candidate Stocks</div>'
        '<div class="candidate-note">Our TP e a media dos 5 modelos internos; Consensus fica como referencia dos analistas. '
        'Buy-in usa Our TP e margem de seguranca; a tabela segue do maior para o menor upside.</div>'
    )
    # Keep Billfish, brokerage activity and Open Finance together. Candidate
    # stocks start on a fresh page so the B3 table never competes for space.
    brokerage_needs_own_space = True
    candidate_b3_inline_block = "" if brokerage_needs_own_space else f"{candidate_b3_intro}\n{candidate_b3_panel}"
    candidate_b3_extra_section = ""
    if brokerage_needs_own_space:
        candidate_b3_extra_section = f"""
  <section class="page compact b3-candidates-page b3-candidates-extra-page">
    {candidate_b3_intro}
    {candidate_b3_panel}

    <div class="footer"><span>Chief of Staff Digital - oportunidades</span><span>Pagina 4</span></div>
  </section>
"""
    us_footer_page = 5 if brokerage_needs_own_space else 4
    forecast_footer_page = us_footer_page + 1
    news_footer_page = forecast_footer_page + 1
    agenda_footer_page = news_footer_page + 1
    world_footer_page = agenda_footer_page + 1
    priority_rows = "\n".join(
        f"<div class='priority'><span>{idx}</span><p>{html.escape(priority)}</p></div>"
        for idx, priority in enumerate(priorities, 1)
    )
    event_rows = "\n".join(render_event_card_html(e) for e in events) or "<div class='empty'>Sem compromissos encontrados na agenda.</div>"
    forecast_panel = render_forecast_panel_html(forecast or {})
    news_panel = render_news_table_html(news or [])
    action_brief_panel = render_action_brief_panel_html(
        build_decision_queue(important),
        build_followups(important, day),
    )
    automation_health_panel = render_automation_health_html(automation_health or [])
    world_cup_panel = render_world_cup_panel_html(world_cup or {})

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>{html.escape(report_title)} - {day.strftime('%d/%m/%Y')}</title>
  <style>
    @page {{ size: A4; margin: 0; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #eef1f4;
      color: #111827;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      font-size: 12px;
      line-height: 1.35;
    }}
    .page {{
      width: 210mm;
      min-height: 297mm;
      padding: 15mm 16mm 14mm;
      background: #ffffff;
      page-break-after: always;
      position: relative;
    }}
    .page:last-child {{ page-break-after: auto; }}
    .page.compact {{ padding-top: 11mm; }}
    .page.us-candidates {{ padding-top: 15mm; }}
    .hero {{
      background: #101820;
      color: #ffffff;
      padding: 15mm 14mm 10mm;
      margin: -15mm -16mm 6mm;
      border-bottom: 5px solid #b8a46f;
    }}
    .eyebrow {{
      color: #b8c0cc;
      font-size: 9px;
      font-weight: 800;
      letter-spacing: 1.7px;
      text-transform: uppercase;
      margin-bottom: 5mm;
    }}
    .hero-grid {{ display: grid; grid-template-columns: 1fr auto; gap: 18mm; align-items: end; }}
    h1 {{ font-size: 34px; line-height: 1; margin: 0 0 4mm; letter-spacing: 0; }}
    .subtitle {{ color: #d7dde5; font-size: 13px; }}
    .generated {{ color: #d7dde5; text-align: right; font-size: 11px; line-height: 1.45; }}
    .stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 3mm; margin: 0 0 4mm; }}
    .stat {{ border: 1px solid #d9dee7; padding: 2.8mm 4mm; background: #f8fafc; min-height: 19mm; }}
    .stat-label {{ color: #516070; font-size: 10px; font-weight: 800; }}
    .stat-value {{ font-size: 24px; font-weight: 800; line-height: 1; margin-top: 1.2mm; }}
    .stat-note {{ color: #667085; font-size: 10px; margin-top: 1mm; }}
    .section-title {{
      display: flex;
      align-items: center;
      gap: 3mm;
      margin: 3.5mm 0 2mm;
      color: #111827;
      font-size: 13px;
      font-weight: 850;
      letter-spacing: .5px;
      text-transform: uppercase;
      break-after: avoid;
      page-break-after: avoid;
    }}
    .section-title + table,
    .section-title + .news-grid,
    .section-title + .card,
    .section-title + .empty {{ break-before: avoid; page-break-before: avoid; }}
    .page.compact .section-title:first-child {{ margin-top: 0; }}
    .candidate-stocks-title {{ margin-top: 8mm; }}
    .daily-priorities-title {{ margin-top: 13.5mm; }}
    .news-title {{ break-before: page; page-break-before: always; margin-top: 10mm; padding-top: 0; }}
    .agenda-title {{ break-before: page; page-break-before: always; margin-top: 10mm; padding-top: 0; }}
    .world-cup-title {{ break-before: page; page-break-before: always; margin-top: 10mm; padding-top: 0; }}
    .section-title:before {{ content: ""; width: 6mm; height: 2px; background: #b8a46f; display: block; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{
      text-align: left;
      color: #52616f;
      background: #f1f4f7;
      font-size: 10px;
      padding: 8px 10px;
      text-transform: uppercase;
      letter-spacing: .35px;
    }}
    td {{ border-bottom: 1px solid #e7ebf0; padding: 8px 10px; vertical-align: top; }}
    .market th {{ padding: 5px 10px; }}
    .market td {{ padding: 3px 10px; }}
    .market.stocks th {{ padding-top: 4px; padding-bottom: 4px; }}
    .market.stocks td {{ padding-top: 2px; padding-bottom: 2px; font-size: 11.6px; line-height: 1.18; }}
    .market td:nth-child(2), .market td:nth-child(4) {{ white-space: nowrap; }}
    .market:not(.stocks):not(.crypto):not(.index) td:nth-child(4),
    .market.index td:nth-child(5),
    .market.crypto td:nth-child(5) {{ font-style: italic; }}
    .market.index td:nth-child(3), .market.index td:nth-child(4), .market.index td:nth-child(5) {{ white-space: nowrap; }}
    .market.stocks td:nth-child(3), .market.stocks td:nth-child(5), .market.stocks td:nth-child(6) {{ white-space: nowrap; }}
    .market.stocks td:nth-child(3) {{ font-weight: 800; }}
    .market.stocks td:nth-child(5), .market.stocks td:nth-child(6) {{ font-style: italic; }}
    .market-group {{ margin-bottom: 2.7mm; }}
    .market-group:last-child {{ margin-bottom: 0; }}
    .market-group-title {{
      font-size: 10px;
      font-weight: 850;
      color: #8a6f2a;
      text-transform: uppercase;
      letter-spacing: .7px;
      margin: 0 0 1mm;
    }}
    .asset {{ font-weight: 800; }}
    .market.stocks th:first-child, .market.crypto th:first-child, .market.index th:first-child, .logo-cell {{ width: 78px; padding-right: 7px; }}
    .company-logo {{
      width: 60px;
      height: 16px;
      display: inline-flex;
      align-items: center;
      justify-content: flex-start;
      vertical-align: middle;
    }}
    .company-logo svg {{ width: 60px; height: 16px; display: block; }}
    .pos {{ color: #087443; font-weight: 800; }}
    .neg {{ color: #b42318; font-weight: 800; }}
    .muted {{ color: #667085; }}
    .billfish {{
      border: 1px solid #d9dee7;
      display: grid;
      grid-template-columns: 1.05fr .95fr;
      margin-top: 2mm;
    }}
    .bill-main {{ padding: 5mm; background: #fbfcfe; border-right: 1px solid #d9dee7; }}
    .bill-main h3 {{ margin: 0 0 4mm; font-size: 19px; }}
    .bill-meta {{ color: #667085; font-size: 10px; }}
    .bill-kpis {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 3mm; margin-top: 5mm; }}
    .kpi {{ border-top: 1px solid #d9dee7; padding-top: 3mm; }}
    .kpi-label {{ color: #667085; font-size: 9px; text-transform: uppercase; font-weight: 800; }}
    .kpi-value {{ margin-top: 1mm; font-size: 15px; font-weight: 850; }}
    .perf {{ padding: 5mm; }}
    .perf-title {{ font-weight: 850; margin-bottom: 3mm; text-align: center; }}
    .brokerage-notes {{
      border: 1px solid #d9dee7;
      background: #fbfcfe;
      padding: 2.6mm;
      margin-top: 2mm;
      break-inside: auto;
      page-break-inside: auto;
    }}
    .brokerage-summary {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 2mm;
      margin-bottom: 1.6mm;
    }}
    .brokerage-kpi {{
      border-top: 1px solid #d9dee7;
      padding-top: 1.8mm;
    }}
    .brokerage-kpi-label {{
      color: #667085;
      font-size: 7.6px;
      font-weight: 850;
      letter-spacing: .35px;
      text-transform: uppercase;
    }}
    .brokerage-kpi-value {{
      color: #111827;
      font-size: 10.6px;
      font-weight: 900;
      margin-top: .5mm;
    }}
    .brokerage-table th {{ font-size: 7.1px; padding: 3px 4px; }}
    .brokerage-table td {{ font-size: 7.8px; line-height: 1.08; padding: 3px 4px; }}
    .brokerage-table td:nth-child(1),
    .brokerage-table td:nth-child(2),
    .brokerage-table td:nth-child(4),
    .brokerage-table td:nth-child(5),
    .brokerage-table td:nth-child(6) {{ white-space: nowrap; }}
    .brokerage-asset {{ font-weight: 900; color: #111827; }}
    .brokerage-financial {{ margin-top: 1.6mm; border-top: 1px solid #d9dee7; padding-top: 1.5mm; }}
    .brokerage-financial-title {{ color: #667085; font-size: 7.2px; font-weight: 850; letter-spacing: .35px; text-transform: uppercase; margin-bottom: 1mm; }}
    .brokerage-financial-grid {{ display: flex; flex-wrap: wrap; gap: 1mm 2mm; }}
    .brokerage-financial-chip {{ display: inline-flex; gap: 1mm; align-items: baseline; color: #667085; font-size: 7.5px; white-space: nowrap; }}
    .brokerage-financial-chip strong {{ color: #111827; font-size: 7.7px; }}
    .brokerage-financial-chip strong.pos {{ color: #047857; }}
    .brokerage-financial-chip strong.neg {{ color: #b42318; }}
    .priority-grid {{ display: grid; gap: 3mm; }}
    .priority {{ display: grid; grid-template-columns: 9mm 1fr; gap: 3mm; border-left: 3px solid #b8a46f; background: #f8fafc; padding: 3.5mm; }}
    .priority span {{ font-weight: 850; color: #8a6f2a; }}
    .priority p {{ margin: 0; }}
    .forecast-box {{ border: 1px solid #d9dee7; background: #fbfcfe; padding: 4mm; margin-bottom: 3mm; }}
    .forecast-grid {{ display: grid; grid-template-columns: 1fr; gap: 2.5mm; }}
    .forecast-grid .forecast-box {{ padding: 3mm; margin-bottom: 2mm; }}
    .forecast-main {{ display: grid; grid-template-columns: 1fr auto; gap: 6mm; align-items: start; }}
    .forecast-place {{
      display: flex;
      align-items: center;
      gap: 2.5mm;
      min-width: 0;
    }}
    .forecast-condition-icon {{
      width: 13mm;
      height: 13mm;
      border-radius: 50%;
      background: #f1f4f7;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex: 0 0 auto;
    }}
    .forecast-condition-icon svg {{ width: 10.5mm; height: 10.5mm; display: block; }}
    .forecast-location {{ font-weight: 850; font-size: 13px; }}
    .forecast-desc {{ color: #52616f; margin-top: 1mm; }}
    .forecast-temp {{ font-size: 20px; font-weight: 900; color: #111827; text-align: right; }}
    .forecast-meta {{ color: #667085; font-size: 10px; text-align: right; margin-top: 1mm; }}
    .forecast-grid .forecast-main {{ grid-template-columns: 1fr auto; gap: 5mm; }}
    .forecast-grid .forecast-condition-icon {{ width: 11mm; height: 11mm; }}
    .forecast-grid .forecast-condition-icon svg {{ width: 8.8mm; height: 8.8mm; }}
    .forecast-grid .forecast-location {{ font-size: 12px; }}
    .forecast-grid .forecast-desc {{ font-size: 9px; margin-top: .5mm; }}
    .forecast-grid .forecast-temp {{ font-size: 17px; text-align: right; margin-top: 0; }}
    .forecast-grid .forecast-meta {{ font-size: 8.5px; text-align: right; }}
    .forecast-days {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 2mm; margin-top: 3mm; }}
    .forecast-day {{ border-top: 1px solid #e7ebf0; padding-top: 2mm; }}
    .forecast-date {{ color: #667085; font-size: 9px; font-weight: 800; text-transform: uppercase; }}
    .forecast-range {{ font-weight: 850; margin-top: .5mm; }}
    .forecast-rain {{ color: #52616f; font-size: 10px; margin-top: .5mm; }}
    .forecast-grid .forecast-days {{ gap: 1.2mm; margin-top: 2mm; }}
    .forecast-grid .forecast-day {{ padding-top: 1.2mm; }}
    .forecast-grid .forecast-date {{ font-size: 7.8px; }}
    .forecast-grid .forecast-range {{ font-size: 8.5px; }}
    .forecast-grid .forecast-rain {{ font-size: 7.8px; }}
    .forecast-hourly {{ margin-top: 3mm; border-top: 1px solid #e7ebf0; padding-top: 2.5mm; }}
    .forecast-hourly-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1mm; }}
    .forecast-hourly-title {{ font-size: 9px; font-weight: 850; color: #52616f; text-transform: uppercase; letter-spacing: .35px; }}
    .forecast-legend {{ display: flex; gap: 3mm; color: #667085; font-size: 9px; }}
    .legend-temp:before, .legend-rain:before {{ content: ""; display: inline-block; width: 9px; height: 3px; margin-right: 4px; vertical-align: middle; }}
    .legend-temp:before {{ background: #175cd3; }}
    .legend-rain:before {{ background: #89c2ff; }}
    .forecast-chart {{ width: 100%; height: 35mm; display: block; }}
    .forecast-axis {{ stroke: #d9dee7; stroke-width: 1; }}
    .forecast-gridline {{ stroke: #eef2f6; stroke-width: 1; }}
    .forecast-temp-line {{ fill: none; stroke: #175cd3; stroke-width: 2.2; }}
    .forecast-temp-dot {{ fill: #175cd3; }}
    .forecast-rain-bar {{ fill: #89c2ff; opacity: .72; }}
    .forecast-hour-label {{ fill: #667085; font-size: 9px; font-weight: 700; }}
    .forecast-temp-label {{ fill: #175cd3; font-size: 12px; font-weight: 850; }}
    .forecast-rain-label {{ fill: #52616f; font-size: 10.5px; font-weight: 780; }}
    .forecast-grid .forecast-hourly {{ margin-top: 2mm; padding-top: 2mm; }}
    .forecast-grid .forecast-chart {{ height: 29mm; }}
    .forecast-mini {{ margin-top: 1mm; }}
    .forecast-mini th {{ padding: 5px 8px; font-size: 8.5px; }}
    .forecast-mini td {{ padding: 5px 8px; font-size: 9px; }}
    .forecast-mini td:nth-child(3),
    .forecast-mini td:nth-child(4),
    .forecast-mini td:nth-child(5) {{ white-space: nowrap; }}
    .forecast-summary-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 2.4mm;
      margin-top: 2.2mm;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .forecast-summary-card {{
      display: grid;
      grid-template-columns: 17mm 1fr;
      gap: 2.6mm;
      align-items: center;
      border: 1px solid #d9dee7;
      background: #fff;
      padding: 2.8mm 3mm;
      min-height: 25mm;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .forecast-summary-icon {{
      width: 15mm;
      height: 15mm;
      border-radius: 50%;
      background: #f1f4f7;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .forecast-summary-icon svg {{ width: 12mm; height: 12mm; display: block; }}
    .forecast-summary-place {{ font-size: 10.5px; font-weight: 850; color: #111827; }}
    .forecast-summary-condition {{ color: #52616f; font-size: 8.6px; margin-top: .3mm; }}
    .forecast-summary-metrics {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1.4mm;
      margin-top: 1.8mm;
    }}
    .forecast-summary-metric span {{
      display: block;
      color: #667085;
      font-size: 7.2px;
      font-weight: 850;
      letter-spacing: .25px;
      text-transform: uppercase;
    }}
    .forecast-summary-metric strong {{
      display: block;
      color: #111827;
      font-size: 8.8px;
      line-height: 1.15;
      margin-top: .4mm;
    }}
    .open-finance-title {{ margin-top: 4mm; }}
    .open-finance-card {{
      border: 1px solid #d9dee7;
      background: #fbfcfe;
      padding: 3mm;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .open-finance-empty {{ padding: 4mm; }}
    .open-finance-kpis {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 2mm;
      margin-bottom: 2.8mm;
    }}
    .open-finance-kpi {{
      background: #fff;
      border: 1px solid #e7ebf0;
      padding: 2.2mm 2.4mm;
      min-height: 14mm;
    }}
    .open-finance-kpi span {{
      display: block;
      color: #667085;
      font-size: 7.6px;
      font-weight: 850;
      text-transform: uppercase;
      letter-spacing: .35px;
    }}
    .open-finance-kpi strong {{
      display: block;
      color: #111827;
      font-size: 12.8px;
      line-height: 1.1;
      margin-top: 1mm;
      white-space: nowrap;
    }}
    .open-finance-products {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 3mm;
    }}
    .open-finance-products-bottom {{ margin-top: 3mm; align-items: start; }}
    .open-finance-pane {{ min-width: 0; }}
    .open-finance-subtitle {{
      color: #8a6f2a;
      font-size: 8.4px;
      font-weight: 850;
      letter-spacing: .6px;
      text-transform: uppercase;
      margin-bottom: 1.2mm;
    }}
    .open-finance-table {{ table-layout: fixed; width: 100%; }}
    .open-finance-table th {{ font-size: 7.2px; padding: 4px 5px; }}
    .open-finance-table td {{ font-size: 7.8px; line-height: 1.12; padding: 4px 5px; vertical-align: top; }}
    .open-finance-table td span {{
      display: block;
      color: #667085;
      font-size: 7px;
      line-height: 1.08;
      margin-top: .4mm;
    }}
    .open-finance-table td:last-child {{ text-align: right; white-space: nowrap; font-weight: 850; }}
    .open-finance-accounts th:nth-child(1) {{ width: 31%; }}
    .open-finance-accounts th:nth-child(2) {{ width: 43%; }}
    .open-finance-accounts th:nth-child(3) {{ width: 26%; }}
    .open-finance-cards th:nth-child(1) {{ width: 25%; }}
    .open-finance-cards th:nth-child(2) {{ width: 39%; }}
    .open-finance-cards th:nth-child(3) {{ width: 22%; }}
    .open-finance-cards th:nth-child(4) {{ width: 14%; }}
    .open-finance-investments th:nth-child(1) {{ width: 30%; }}
    .open-finance-investments th:nth-child(2) {{ width: 43%; }}
    .open-finance-investments th:nth-child(3) {{ width: 27%; }}
    .open-finance-expenses th:nth-child(1) {{ width: 37%; }}
    .open-finance-expenses th:nth-child(n+2) {{ width: 21%; text-align: right; }}
    .open-finance-expenses td:nth-child(n+2) {{ text-align: right; white-space: nowrap; }}
    .open-finance-expenses td:nth-child(3) {{ color: #175cd3; font-weight: 800; }}
    .open-finance-bank {{ display: inline-flex; align-items: center; gap: 1.1mm; min-width: 0; }}
    .open-finance-bank-logo {{ width: 5mm; height: 5mm; flex: 0 0 5mm; display: inline-flex; }}
    .open-finance-bank-logo svg {{ width: 5mm; height: 5mm; display: block; }}
    .open-finance-bank-name {{ color: #111827; font-size: 7.5px; font-weight: 800; line-height: 1.05; }}
    .money-positive {{ color: #047857; }}
    .money-negative {{ color: #b42318; }}
    .open-finance-note,
    .open-finance-warning {{
      color: #667085;
      font-size: 7.5px;
      margin-top: 1.5mm;
      line-height: 1.18;
    }}
    .open-finance-warning {{ color: #b54708; }}
    .statements-page {{ padding-top: 12mm; }}
    .statements-page .section-title {{ margin-bottom: 1.2mm; }}
    .statement-period {{ color: #667085; font-size: 8.2px; margin: 0 0 3mm 9mm; }}
    .statement-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 3mm;
      align-items: start;
    }}
    .statement-bank {{
      min-width: 0;
      border: 1px solid #d9dee7;
      background: #fbfcfe;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .statement-bank-head {{ padding: 3mm; background: #fff; border-bottom: 1px solid #d9dee7; }}
    .statement-bank-identity {{ display: flex; align-items: center; gap: 2mm; min-width: 0; }}
    .statement-bank-logo {{ width: 7.5mm; height: 7.5mm; flex: 0 0 7.5mm; }}
    .statement-bank-logo svg {{ width: 7.5mm; height: 7.5mm; display: block; }}
    .statement-bank-name {{ color: #111827; font-size: 10.2px; font-weight: 900; line-height: 1.05; }}
    .statement-bank-count {{ color: #667085; font-size: 6.9px; margin-top: .7mm; }}
    .statement-bank-kpis {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1mm; margin-top: 2.4mm; }}
    .statement-bank-kpi {{ min-width: 0; border-top: 2px solid #d9dee7; padding-top: 1.2mm; }}
    .statement-bank-kpi.income {{ border-color: #6bc5a3; }}
    .statement-bank-kpi.outflow {{ border-color: #e7a09a; }}
    .statement-bank-kpi.balance {{ border-color: #8aa8dc; }}
    .statement-bank-kpi span {{ display: block; color: #667085; font-size: 5.9px; font-weight: 850; text-transform: uppercase; }}
    .statement-bank-kpi strong {{ display: block; color: #111827; font-size: 7px; margin-top: .5mm; white-space: nowrap; }}
    .statement-date {{
      color: #52616f;
      background: #f1f4f7;
      border-bottom: 1px solid #d9dee7;
      padding: 1.2mm 2.2mm;
      font-size: 6.8px;
      font-weight: 900;
      letter-spacing: .25px;
      text-transform: uppercase;
    }}
    .statement-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 1.4mm;
      align-items: start;
      padding: 1.5mm 2.2mm;
      border-bottom: 1px solid #e7ebf0;
      background: #fff;
    }}
    .statement-row:last-child {{ border-bottom: 0; }}
    .statement-description {{
      color: #111827;
      font-size: 7.35px;
      font-weight: 760;
      line-height: 1.08;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .statement-meta {{
      color: #667085;
      font-size: 6.05px;
      line-height: 1.08;
      margin-top: .65mm;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .statement-amount {{ font-size: 7.3px; font-weight: 900; white-space: nowrap; text-align: right; }}
    .statement-empty {{ color: #667085; background: #fff; padding: 8mm 3mm; text-align: center; font-size: 7.5px; }}
    .statement-overflow {{ color: #667085; background: #f8fafc; padding: 1.6mm 2.2mm; font-size: 6.5px; font-style: italic; }}
    .statement-warning {{ color: #b54708; font-size: 7px; margin-top: 2mm; }}
    .news-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 3mm; margin-top: 1mm; }}
    .news-box {{ border: 1px solid #d9dee7; background: #fff; padding: 3mm; break-inside: avoid; page-break-inside: avoid; }}
    .news-box-head {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 2mm; }}
    .news-logo {{ height: 8mm; display: inline-flex; align-items: center; }}
    .news-logo svg {{ display: block; max-width: 31mm; height: 7mm; }}
    .news-count {{ color: #667085; font-size: 7.8px; font-weight: 800; text-transform: uppercase; letter-spacing: .35px; }}
    .news-items {{ display: grid; gap: 1.6mm; }}
    .news-item {{ border-top: 1px solid #e7ebf0; padding-top: 1.6mm; }}
    .news-item:first-child {{ border-top: 0; padding-top: 0; }}
    .news-link {{ color: #111827; font-size: 9.8px; line-height: 1.2; font-weight: 780; text-decoration: none; }}
    .news-time {{ color: #667085; font-size: 7.8px; margin-top: .7mm; }}
    .news-error {{ color: #b42318; font-size: 8.5px; line-height: 1.25; }}
    .action-briefs {{ display: grid; gap: 2.2mm; margin: 3mm 0 1mm; }}
    .action-brief-box {{ border: 1px solid #d9dee7; background: #fff; padding: 2.4mm; break-inside: avoid; page-break-inside: avoid; }}
    .action-brief-title {{ color: #8a6f2a; font-size: 9.5px; font-weight: 850; letter-spacing: .6px; text-transform: uppercase; margin-bottom: 1.4mm; }}
    .action-table th {{ font-size: 7.8px; padding: 4px 6px; }}
    .action-table td {{ font-size: 8.4px; line-height: 1.18; padding: 4.5px 6px; }}
    .action-table td:first-child {{ font-weight: 800; color: #111827; }}
    .world-cup-card {{
      border: 1px solid #d9dee7;
      background: #fbfcfe;
      padding: 3.2mm;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .world-cup-table th {{ font-size: 8.2px; padding: 5px 7px; }}
    .world-cup-table td {{ font-size: 8.8px; line-height: 1.14; padding: 4.8px 7px; }}
    .world-cup-table td:nth-child(2) {{ font-weight: 850; color: #111827; }}
    .world-cup-table td:nth-child(3) {{ white-space: nowrap; }}
    .world-cup-block {{ margin-bottom: 2.8mm; }}
    .world-cup-block + .world-cup-block {{
      border-top: 1px solid #d9dee7;
      padding-top: 2.4mm;
    }}
    .world-cup-block-title {{
      color: #8a6f2a;
      font-size: 9px;
      font-weight: 850;
      letter-spacing: .6px;
      text-transform: uppercase;
      margin-bottom: 1.4mm;
    }}
    .world-cup-location {{ color: #111827; font-weight: 700; }}
    .world-cup-location span {{ color: #667085; font-weight: 650; }}
    .world-cup-fixtures-table td:nth-child(2) {{ white-space: nowrap; }}
    .world-cup-fixtures-table td:nth-child(3) {{ white-space: normal; }}
    .world-cup-fixtures-table .world-cup-match {{
      width: 86mm;
      max-width: 100%;
    }}
    .world-cup-status {{
      display: inline-block;
      min-width: 20mm;
      text-align: center;
      color: #344054;
      background: #eef2f6;
      font-size: 7.5px;
      font-weight: 850;
      text-transform: uppercase;
      padding: 2px 5px;
    }}
    .world-cup-status.result {{ color: #087443; background: #e7f6ee; }}
    .world-cup-status.fixture {{ color: #175cd3; background: #eef4ff; }}
    .world-cup-detail {{ font-size: 10.8px; font-weight: 900; color: #111827; }}
    .world-cup-detail.time {{ color: #175cd3; }}
    .world-cup-source {{ color: #667085; font-size: 8px; margin-top: 2mm; }}
    .reading-news-page .news-title,
    .reading-agenda-page .agenda-title,
    .reading-world-page .world-cup-title {{
      break-before: auto;
      page-break-before: auto;
      margin-top: 0;
    }}
    .reading-world-page {{ padding-top: 10mm; padding-bottom: 10mm; }}
    .reading-world-page .brasileirao-card {{ padding: 2.1mm; }}
    .reading-world-page .brasileirao-standings-table td {{ padding-top: 2.35px; padding-bottom: 2.35px; }}
    .reading-world-page .brasileirao-matches-table td {{ padding-top: 2.6px; padding-bottom: 2.6px; }}
    .reading-world-page .brasileirao-scorers .world-cup-scorers-table td {{ padding-top: 3px; padding-bottom: 3px; }}
    .reading-world-page .automation-health {{ margin-top: 2mm; padding-top: 1.5mm; }}
    .reading-world-page .automation-health-grid {{ grid-template-columns: repeat(6, 1fr); gap: 1.1mm; }}
    .reading-world-page .health-item {{ min-height: 10mm; padding: 1.2mm 1.3mm; }}
    .reading-world-page .health-label {{ font-size: 6.5px; }}
    .reading-world-page .health-value {{ font-size: 7.3px; margin-top: .5mm; }}
    .world-cup-match {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 8mm minmax(0, 1fr);
      align-items: center;
      column-gap: 1.6mm;
      width: 100%;
      font-weight: 850;
    }}
    .world-cup-match-side {{
      display: flex;
      align-items: center;
      min-width: 0;
    }}
    .world-cup-match-side.home {{
      justify-content: flex-end;
      text-align: right;
    }}
    .world-cup-match-side.away {{
      justify-content: flex-start;
      text-align: left;
    }}
    .world-cup-team {{
      display: inline-flex;
      align-items: center;
      gap: 1.8mm;
      font-size: 10.8px;
      font-weight: 900;
      white-space: nowrap;
    }}
    .world-cup-flag {{
      width: 16px;
      height: 16px;
      border-radius: 50%;
      object-fit: cover;
      border: 1px solid #d9dee7;
      background: #fff;
      flex: 0 0 auto;
    }}
    .world-cup-vs {{
      display: block;
      width: 100%;
      text-align: center;
      color: #667085;
      font-size: 7.3px;
      font-weight: 850;
      letter-spacing: .45px;
      text-transform: uppercase;
    }}
    .world-cup-team-with-flag {{
      display: inline-flex;
      align-items: center;
      gap: 1.6mm;
      white-space: nowrap;
    }}
    .world-cup-result-match {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 8mm 8mm 8mm minmax(0, 1fr);
      align-items: center;
      column-gap: 0;
      width: 100%;
    }}
    .world-cup-result-side {{
      display: flex;
      align-items: center;
      gap: 1.8mm;
      min-width: 0;
    }}
    .world-cup-result-side.home {{ justify-content: flex-end; text-align: right; }}
    .world-cup-result-side.away {{ justify-content: flex-start; text-align: left; }}
    .world-cup-result-score {{
      color: #111827;
      font-size: 10.8px;
      font-weight: 950;
      text-align: center;
      white-space: nowrap;
    }}
    .world-cup-scorers {{
      margin-top: 3mm;
      border-top: 1px solid #d9dee7;
      padding-top: 2.4mm;
    }}
    .world-cup-scorers-title {{
      color: #8a6f2a;
      font-size: 9px;
      font-weight: 850;
      letter-spacing: .6px;
      text-transform: uppercase;
      margin-bottom: 1.4mm;
    }}
    .world-cup-scorers-table th {{ font-size: 9.8px; padding: 5px 7px; }}
    .world-cup-scorers-table td {{ font-size: 10.8px; line-height: 1.15; padding: 5px 7px; }}
    .world-cup-scorers-table td:first-child,
    .world-cup-scorers-table td:last-child,
    .world-cup-scorers-table td:nth-child(4) {{ white-space: nowrap; }}
    .world-cup-scorer-rank {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: #eef2f6;
      color: #344054;
      font-size: 7.5px;
      font-weight: 900;
    }}
    .world-cup-goals {{ color: #111827; font-weight: 900; }}
    .brasileirao-card {{ padding: 2.6mm; }}
    .brasileirao-standings-block {{ margin-bottom: 2.4mm; }}
    .brasileirao-standings-table th {{ font-size: 7.1px; padding: 3px 4px; }}
    .brasileirao-standings-table td {{ font-size: 7.6px; line-height: 1.05; padding: 2.7px 4px; }}
    .brasileirao-standings-table td:nth-child(2) {{ width: 42mm; }}
    .brasileirao-standings-table .world-cup-team {{ font-size: 7.8px; font-weight: 850; gap: 1.1mm; }}
    .brasileirao-standings-table .world-cup-flag {{ width: 12px; height: 12px; border-radius: 3px; }}
    .brasileirao-rank {{ color: #667085; font-weight: 850; text-align: center; }}
    .brasileirao-match-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 2.4mm;
      align-items: start;
    }}
    .brasileirao-matches-block {{ margin-bottom: 1.8mm; }}
    .brasileirao-matches-block + .brasileirao-matches-block {{ border-top: 0; padding-top: 0; }}
    .brasileirao-matches-table {{ table-layout: fixed; width: 100%; }}
    .brasileirao-matches-table th:nth-child(1),
    .brasileirao-matches-table td:nth-child(1) {{ width: 45%; }}
    .brasileirao-matches-table th:nth-child(2),
    .brasileirao-matches-table td:nth-child(2) {{ width: 20%; text-align: center; }}
    .brasileirao-matches-table th:nth-child(3),
    .brasileirao-matches-table td:nth-child(3) {{ width: 35%; white-space: normal !important; }}
    .brasileirao-matches-table th {{ font-size: 7px; padding: 3.5px 4px; }}
    .brasileirao-matches-table td {{ font-size: 7.3px; line-height: 1.08; padding: 3px 4px; vertical-align: top; }}
    .brasileirao-match-label {{
      display: block;
      color: #111827;
      font-size: 7.6px;
      line-height: 1.08;
      white-space: normal;
    }}
    .brasileirao-matches-table .world-cup-match {{
      grid-template-columns: minmax(0, 1fr) 5mm minmax(0, 1fr);
      column-gap: .8mm;
      width: 100%;
    }}
    .brasileirao-matches-table .world-cup-team {{ font-size: 7.5px; font-weight: 850; gap: .8mm; }}
    .brasileirao-matches-table .world-cup-flag {{ width: 11px; height: 11px; border-radius: 3px; }}
    .brasileirao-matches-table .world-cup-detail {{ font-size: 7.8px; }}
    .brasileirao-matches-table .world-cup-location {{
      display: block;
      max-width: 100%;
      white-space: normal;
      overflow-wrap: anywhere;
      font-size: 7.1px;
      line-height: 1.05;
    }}
    .brasileirao-scorers {{ margin-top: 2.2mm; padding-top: 1.8mm; }}
    .brasileirao-scorers .world-cup-scorers-title {{ font-size: 8.2px; margin-bottom: 1mm; }}
    .brasileirao-scorers .world-cup-scorers-table th {{ font-size: 7.2px; padding: 3.5px 5px; }}
    .brasileirao-scorers .world-cup-scorers-table td {{ font-size: 8px; padding: 3.5px 5px; }}
    .brasileirao-scorers .world-cup-team {{ font-size: 8px; font-weight: 850; }}
    .brasileirao-scorers .world-cup-flag {{ border-radius: 3px; }}
    .automation-health {{
      border-top: 1px solid #d9dee7;
      margin-top: 4mm;
      padding-top: 2.4mm;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .automation-health-title {{
      color: #667085;
      font-size: 8px;
      font-weight: 850;
      letter-spacing: .7px;
      text-transform: uppercase;
      margin-bottom: 1.6mm;
    }}
    .automation-health-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 1.6mm; }}
    .health-item {{ background: #f8fafc; border: 1px solid #e7ebf0; padding: 1.7mm 1.8mm; min-height: 12mm; }}
    .health-label {{ color: #667085; font-size: 7.5px; font-weight: 850; text-transform: uppercase; letter-spacing: .3px; }}
    .health-value {{ color: #111827; font-size: 8.4px; font-weight: 800; line-height: 1.15; margin-top: .8mm; }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }}
    .card {{ border: 1px solid #d9dee7; background: #fff; padding: 4mm; margin-bottom: 3mm; break-inside: avoid; }}
    .card-head {{ display: flex; justify-content: space-between; gap: 4mm; margin-bottom: 2mm; }}
    .card-title {{ font-weight: 850; font-size: 13px; }}
    .badge {{ display: inline-block; font-size: 9px; font-weight: 850; text-transform: uppercase; padding: 2px 6px; background: #eef2f6; color: #344054; }}
    .badge.high {{ background: #fff3e8; color: #b54708; }}
    .badge.reply {{ background: #eef4ff; color: #175cd3; }}
    .email-card {{ border-left: 3px solid #d0d7de; }}
    .email-card.high {{ border-left-color: #d98b31; }}
    .email-card.reply {{ border-left-color: #2f6fed; }}
    .label {{ color: #667085; font-size: 10px; font-weight: 800; text-transform: uppercase; }}
    .empty {{ color: #667085; border: 1px dashed #cfd6df; padding: 5mm; background: #fbfcfe; }}
    .candidate-note {{ color: #667085; font-size: 9px; margin: -1mm 0 3mm 9mm; }}
    .candidate-group {{ margin-bottom: 4mm; break-inside: avoid; }}
    .candidate-group.nasdaq {{ padding-top: 0; }}
    .candidate-group.nyse {{ padding-top: 4mm; }}
    .candidate-group-title {{
      color: #8a6f2a;
      font-size: 10px;
      font-weight: 850;
      letter-spacing: .7px;
      text-transform: uppercase;
      margin-bottom: 2mm;
    }}
    .candidate-table th, .candidate-table td {{ padding: 4px 5px; }}
    .candidate-table td {{ font-size: 9.6px; line-height: 1.18; }}
    .candidate-table th {{ font-size: 9px; }}
    .candidate-table tbody tr:first-child td {{ padding-top: 8px; }}
    .candidate-table th:nth-child(1), .candidate-table td:nth-child(1) {{ width: 24mm; }}
    .candidate-table th:nth-child(2), .candidate-table td:nth-child(2) {{ width: 18mm; white-space: nowrap; }}
    .candidate-table th:nth-child(3), .candidate-table td:nth-child(3) {{ width: 27mm; }}
    .candidate-table th:nth-child(4), .candidate-table td:nth-child(4) {{ width: 30mm; }}
    .candidate-table th:nth-child(5), .candidate-table td:nth-child(5) {{ width: 28mm; }}
    .candidate-table th:nth-child(6), .candidate-table td:nth-child(6) {{ width: 51mm; }}
    .candidate-table td:nth-child(6) {{ font-size: 8.6px; line-height: 1.12; }}
    .b3-candidates-page .candidate-group.b3 {{ margin-top: 7mm; }}
    .b3-candidates-page .candidate-group-title {{ font-size: 10.5px; margin-bottom: 2mm; }}
    .b3-candidates-page .candidate-table th,
    .b3-candidates-page .candidate-table td {{ padding: 4.6px 5.2px; }}
    .b3-candidates-page .candidate-table td {{ font-size: 9.55px; line-height: 1.14; }}
    .b3-candidates-page .candidate-table th {{ font-size: 8.85px; }}
    .b3-candidates-page .candidate-table tbody tr:first-child td {{ padding-top: 7px; }}
    .b3-candidates-page .candidate-table td:nth-child(3) .multiple-lines {{ transform: translateY(1pt); }}
    .b3-candidates-page .candidate-table td:nth-child(6) {{ font-size: 8.45px; line-height: 1.09; }}
    .b3-candidates-page .candidate-brand-logo,
    .b3-candidates-page .candidate-brand-logo svg {{ width: 66px; height: 18px; }}
    .b3-candidates-page .candidate-brand-logo {{ margin-top: 3px; }}
    .b3-candidates-page .candidate-name {{ font-size: 6.9px; line-height: 1.1; }}
    .b3-candidates-page .buy-analysis {{ margin-top: 3px; }}
    .b3-candidates-page .target-upside-label {{ margin-top: 4px; }}
    .b3-candidates-page .section-title {{ margin-top: 2mm; margin-bottom: 1.4mm; }}
    .b3-candidates-page .section-title:first-child {{ margin-top: 0; }}
    .b3-candidates-page .candidate-stocks-title {{ margin-top: 20mm; }}
    .b3-candidates-page .candidate-note {{ font-size: 8.1px; line-height: 1.12; margin: -0.5mm 0 1.2mm 9mm; }}
    .b3-candidates-page .billfish {{ margin-top: 1mm; }}
    .b3-candidates-page .bill-main {{ padding: 3mm; }}
    .b3-candidates-page .bill-main h3 {{ font-size: 16px; margin-bottom: 2mm; }}
    .b3-candidates-page .bill-meta {{ font-size: 8.8px; }}
    .b3-candidates-page .bill-kpis {{ gap: 1.6mm; margin-top: 2.4mm; }}
    .b3-candidates-page .kpi {{ padding-top: 1.5mm; }}
    .b3-candidates-page .kpi-label {{ font-size: 7.6px; }}
    .b3-candidates-page .kpi-value {{ font-size: 12.2px; margin-top: .5mm; }}
    .b3-candidates-page .perf {{ padding: 3mm; }}
    .b3-candidates-page .perf-title {{ font-size: 10px; margin-bottom: 1.4mm; }}
    .b3-candidates-page .perf th {{ font-size: 7.8px; padding: 3.2px 5px; }}
    .b3-candidates-page .perf td {{ font-size: 8.6px; padding: 3.2px 5px; }}
    .b3-candidates-page .brokerage-title {{ margin-top: 7mm; }}
    .b3-candidates-page .open-finance-title {{ margin-top: 7mm; }}
    .b3-candidates-page .open-finance-card {{ margin-top: 5mm; }}
    .b3-candidates-page .brokerage-notes {{ padding: 1.7mm; margin-top: 1mm; }}
    .b3-candidates-page .brokerage-summary {{ gap: 1.3mm; margin-bottom: .9mm; }}
    .b3-candidates-page .brokerage-kpi {{ padding-top: 1mm; }}
    .b3-candidates-page .brokerage-kpi-label {{ font-size: 6.7px; }}
    .b3-candidates-page .brokerage-kpi-value {{ font-size: 9.2px; margin-top: .2mm; }}
    .b3-candidates-page .brokerage-table th {{ font-size: 6.4px; padding: 2px 3px; }}
    .b3-candidates-page .brokerage-table td {{ font-size: 6.9px; line-height: 1.02; padding: 2px 3px; }}
    .b3-candidates-page .brokerage-financial {{ margin-top: .9mm; padding-top: .8mm; }}
    .b3-candidates-page .brokerage-financial-title {{ font-size: 6.6px; margin-bottom: .5mm; }}
    .b3-candidates-page .brokerage-financial-grid {{ gap: .5mm 1.3mm; }}
    .b3-candidates-page .brokerage-financial-chip {{ font-size: 6.8px; }}
    .b3-candidates-page .brokerage-financial-chip strong {{ font-size: 7px; }}
    .b3-candidates-page {{ padding-top: 8.5mm; padding-bottom: 10mm; }}
    .b3-candidates-page .candidate-group,
    .b3-candidates-page .candidate-table,
    .b3-candidates-page .candidate-table tbody {{ break-inside: auto !important; page-break-inside: auto !important; }}
    .b3-candidates-page .candidate-table tr {{ break-inside: avoid; page-break-inside: avoid; }}
    .b3-candidates-page .candidate-group.b3 {{ margin-top: .8mm; }}
    .b3-candidates-page .candidate-group-title {{ font-size: 9.5px; margin-bottom: .8mm; }}
    .b3-candidates-page .candidate-table th,
    .b3-candidates-page .candidate-table td {{ padding: 2.7px 4.2px; }}
    .b3-candidates-page .candidate-table td {{ font-size: 8.35px; line-height: 1.04; }}
    .b3-candidates-page .candidate-table th {{ font-size: 7.85px; padding-top: 2.8px; padding-bottom: 2.8px; }}
    .b3-candidates-page .candidate-table tbody tr:first-child td {{ padding-top: 3px; }}
    .b3-candidates-page .candidate-table td:nth-child(6) {{ font-size: 7.25px; line-height: 1.02; }}
    .b3-candidates-page .multiple-lines {{ font-size: 7.5px; line-height: 1.02; }}
    .b3-candidates-page .candidate-brand-logo,
    .b3-candidates-page .candidate-brand-logo svg {{ width: 54px; height: 13px; }}
    .b3-candidates-page .candidate-brand-logo {{ margin-top: 1px; }}
    .b3-candidates-page .candidate-name {{ font-size: 6.05px; line-height: 1.02; }}
    .b3-candidates-page .target-model-label {{ font-size: 6.4px; }}
    .b3-candidates-page .target-price,
    .b3-candidates-page .model-target-price,
    .b3-candidates-page .target-upside-value {{ font-size: 8px; }}
    .b3-candidates-page .target-analysts,
    .b3-candidates-page .target-upside-label {{ font-size: 6.7px; }}
    .b3-candidates-page .buy-analysis {{ font-size: 7px; line-height: 1.02; margin-top: 1px; }}
    .us-candidates .candidate-group {{ margin-bottom: 3mm; break-inside: auto; }}
    .us-candidates .candidate-group.nyse {{ padding-top: 3mm; }}
    .us-candidates .candidate-table th, .us-candidates .candidate-table td {{ padding: 4.1px 5px; }}
    .us-candidates .candidate-table td {{ font-size: 9.15px; line-height: 1.1; }}
    .us-candidates .candidate-table td:nth-child(6) {{ font-size: 7.75px; line-height: 1.04; }}
    .us-candidates .candidate-table th {{ font-size: 8.45px; }}
    .us-candidates .candidate-table tbody tr:first-child td {{ padding-top: 5px; }}
    .us-candidates .candidate-group-title {{ margin-bottom: 1.4mm; font-size: 10.8px; }}
    .us-candidates .target-upside,
    .us-candidates .price-to-buy-in {{ margin-top: 2px; }}
    .us-candidates .target-upside-label {{ margin-top: 3px; }}
    .us-candidates .buy-analysis {{ margin-top: 3px; font-size: 7.6px; line-height: 1.05; }}
    .us-candidates .multiple-lines {{ font-size: 8.15px; line-height: 1.05; }}
    .us-candidates .candidate-name {{ font-size: 6.9px; line-height: 1.05; }}
    .us-candidates .candidate-brand-logo,
    .us-candidates .candidate-brand-logo svg {{ width: 62px; height: 17px; }}
    .us-candidates .candidate-brand-logo {{ margin-top: 2px; }}
    .us-candidates .target-model-label {{ font-size: 6.9px; }}
    .us-candidates .target-price,
    .us-candidates .model-target-price,
    .us-candidates .target-upside-value {{ font-size: 8.7px; }}
    .us-candidates .target-analysts {{ font-size: 7.6px; }}
    .candidate-ticker {{ color: #111827; }}
    .candidate-ticker-cell {{ display: block; }}
    .candidate-symbol {{ display: block; font-weight: 900; color: #111827; line-height: 1; }}
    .candidate-name {{ display: block; color: #667085; font-size: 7.2px; line-height: 1.14; margin-top: 2px; }}
    .candidate-yahoo-link {{ color: #175cd3; font-weight: 700; text-decoration: none; }}
    .candidate-yahoo-link.candidate-etf-name {{ color: #7c3aed; }}
    .candidate-status-badge {{
      display: inline-block;
      margin-top: 3px;
      padding: 1px 4px;
      border-radius: 3px;
      background: #fff3e8;
      color: #b54708;
      font-size: 6.5px;
      font-weight: 900;
      letter-spacing: .3px;
      text-transform: uppercase;
    }}
    .candidate-brand-logo {{ display: block; width: 74px; height: 22px; margin-top: 4px; overflow: hidden; }}
    .candidate-brand-logo svg {{ width: 74px; height: 22px; display: block; }}
    .candidate-price-line {{ display: flex; align-items: baseline; gap: 4px; white-space: nowrap; }}
    .current-price {{ display: inline-block; color: #111827; font-weight: 900; }}
    .candidate-day-change {{ display: inline-block; font-size: 8.6px; font-weight: 900; }}
    .candidate-day-change.pos {{ color: #057a55; }}
    .candidate-day-change.neg {{ color: #b42318; }}
    .price-to-buy-in {{ display: block; color: #175cd3; font-style: italic; margin-top: 2px; }}
    .target-model-label {{ display: block; color: #667085; font-size: 7.4px; font-weight: 850; letter-spacing: .25px; text-transform: uppercase; }}
    .target-model-label-tp {{ margin-top: 4px; color: #8a6f2a; }}
    .target-price {{ display: block; color: #111827; font-weight: 900; }}
    .model-target-price {{ display: block; color: #8a6f2a; font-weight: 900; }}
    .target-analysts {{ display: block; color: #667085; font-size: 8.7px; margin-top: 1px; }}
    .target-upside-label {{ display: block; color: #175cd3; font-size: 8.4px; font-weight: 700; margin-top: 7px; }}
    .target-upside-value {{ display: block; color: #175cd3; font-size: 9.7px; font-weight: 900; margin-top: 1px; }}
    .buy-price {{ color: #175cd3; font-weight: 900; }}
    .buy-analysis {{ display: block; color: #344054; margin-top: 5px; font-size: calc(1em - 1px); line-height: 1.16; }}
    .multiple-lines {{ display: grid; gap: 1px; font-size: 8.6px; line-height: 1.14; }}
    .multiple-line {{ display: flex; justify-content: space-between; gap: 4px; }}
    .multiple-label {{ color: #667085; font-weight: 500; }}
    .multiple-value {{ color: #111827; font-weight: 500; text-align: right; }}
    .thesis-text {{ color: #047857; font-weight: 700; }}
    .risk-text {{ color: #b42318; font-weight: 700; }}
    .footer {{ position: absolute; left: 16mm; right: 16mm; bottom: 7mm; color: #667085; border-top: 1px solid #d9dee7; padding-top: 3mm; font-size: 9px; display: flex; justify-content: space-between; }}
  </style>
</head>
<body>
  <section class="page">
    <header class="hero">
      <div class="eyebrow">Chief of Staff Digital</div>
      <div class="hero-grid">
        <div>
          <h1>{html.escape(report_title)}</h1>
          <div class="subtitle">Eduardo Castro | {day.strftime('%d/%m/%Y')}</div>
        </div>
        <div class="generated">Gerado em<br>{generated}</div>
      </div>
    </header>

    <div class="stats">{stat_cards}</div>

    <div class="section-title">Markets</div>
    {market_sections}

    <div class="footer"><span>Chief of Staff Digital</span><span>Pagina 1</span></div>
  </section>

  <section class="page compact b3-candidates-page">
    <div class="section-title">Billfish FIA</div>
    {billfish_panel}

    <div class="section-title brokerage-title">Brokerage Notes</div>
    {brokerage_panel}

    <div class="section-title open-finance-title">Open Finance</div>
    {pluggy_panel}

    {candidate_b3_inline_block}

    <div class="footer"><span>Chief of Staff Digital - oportunidades</span><span>Pagina 2</span></div>
  </section>

  <section class="page compact statements-page">
    <div class="section-title">EXTRATOS | ULTIMOS 2 DIAS</div>
    {pluggy_statements_panel}

    <div class="footer"><span>Chief of Staff Digital - Open Finance</span><span>Pagina 3</span></div>
  </section>

  {candidate_b3_extra_section}

  <section class="page compact us-candidates">
    {candidate_us_panel}

    <div class="footer"><span>Chief of Staff Digital - oportunidades</span><span>Pagina {us_footer_page}</span></div>
  </section>

  <section class="page compact reading-forecast-page">
    <div class="section-title">FORECAST</div>
    {forecast_panel}

    <div class="section-title daily-priorities-title">DAILY PRIORITIES</div>
    <div class="priority-grid">{priority_rows}</div>

    <div class="footer"><span>Chief of Staff Digital - modo leitura</span><span>Pagina {forecast_footer_page}</span></div>
  </section>

  <section class="page compact reading-news-page">
    <div class="section-title news-title">NEWS</div>
    {news_panel}
    {action_brief_panel}

    <div class="footer"><span>Chief of Staff Digital - modo leitura</span><span>Pagina {news_footer_page}</span></div>
  </section>

  <section class="page compact reading-agenda-page">
    <div class="section-title agenda-title">Agenda</div>
    {event_rows}

    <div class="footer"><span>Chief of Staff Digital - modo leitura</span><span>Pagina {agenda_footer_page}</span></div>
  </section>

  <section class="page compact reading-world-page">
    <div class="section-title world-cup-title">BRASILEIRAO</div>
    {world_cup_panel}
    {automation_health_panel}

    <div class="footer"><span>Chief of Staff Digital - modo leitura</span><span>Pagina {world_footer_page}</span></div>
  </section>

</body>
</html>"""


def render_market_sections_html(markets):
    groups = [
        ("Index", {"ES=F", "NQ=F", "^N225", "^GDAXI", "000001.SS"}),
        ("Currencies", {"BRL=X", "EURBRL=X", "GBPBRL=X"}),
        ("CRIPTO", {"BTC-USD", "ETH-USD", "SOL-USD", "BONK-USD", "DOGE-USD"}),
        ("Portfolio Stocks", {"AMZN", "AVGO", "VOO", "TTWO", "SPCX", "KWEB", "MHVYF", "PRNR3.SA", "UNIP6.SA"}),
    ]
    by_symbol = {market["symbol"]: market for market in markets}
    sections = []
    for title, symbols in groups:
        include_logo = title == "Portfolio Stocks"
        include_crypto_logo = title == "CRIPTO"
        include_index_logo = title == "Index"
        rows = "\n".join(
            render_market_table_row_html(
                by_symbol[symbol],
                include_logo=include_logo,
                include_crypto_logo=include_crypto_logo,
                include_index_logo=include_index_logo,
            )
            for label, symbol in MARKET_SYMBOLS
            if symbol in symbols and symbol in by_symbol
        )
        if not rows:
            continue
        if include_logo:
            header = "<tr><th></th><th>COMPANY</th><th>PRICE</th><th>CHANGE</th><th>LOW</th><th>HIGH</th></tr>"
        elif include_crypto_logo:
            header = "<tr><th></th><th>COIN</th><th>PRICE (US$)</th><th>CHANGE</th><th>TIME</th></tr>"
        elif include_index_logo:
            header = "<tr><th></th><th>INDEX</th><th>PRICE</th><th>CHANGE</th><th>TIME</th></tr>"
        elif title == "Currencies":
            header = "<tr><th>CURRENCY</th><th>PRICE (R$)</th><th>CHANGE</th><th>TIME</th></tr>"
        else:
            header = "<tr><th>COMPANY</th><th>PRICE</th><th>CHANGE</th><th>TIME</th></tr>"
        table_class = "market stocks" if include_logo else ("market crypto" if include_crypto_logo else ("market index" if include_index_logo else "market"))
        sections.append(
            f"""
            <div class="market-group">
              <div class="market-group-title">{html.escape(title)}</div>
              <table class="{table_class}">
                <thead>{header}</thead>
                <tbody>{rows}</tbody>
              </table>
            </div>"""
        )
    return "\n".join(sections)


def render_pluggy_panel_html(snapshot):
    if not snapshot.get("configured"):
        error = snapshot.get("error", "Pluggy nao configurado")
        return (
            "<div class='open-finance-card open-finance-empty'>"
            f"<div class='muted'>Open Finance nao configurado: {html.escape(error)}.</div>"
            "</div>"
        )
    if not snapshot.get("available"):
        error = snapshot.get("error", "sem dados retornados")
        return (
            "<div class='open-finance-card open-finance-empty'>"
            f"<div class='muted'>Pluggy conectado, mas sem dados para exibir: {html.escape(error)}.</div>"
            "</div>"
        )

    bank_accounts = snapshot.get("bank_accounts") or []
    credit_cards = snapshot.get("credit_cards") or []
    investments = snapshot.get("investments") or []
    expense_categories = snapshot.get("expense_categories") or []
    kpis = [
        ("Saldo corrente", format_pluggy_money(snapshot.get("total_brl"), "BRL")),
        ("Faturas abertas", format_pluggy_money(snapshot.get("total_card_balance_brl"), "BRL")),
        ("Investimentos", format_pluggy_money(snapshot.get("total_investments_brl"), "BRL")),
        ("Despesas 30d", format_pluggy_money(snapshot.get("past_expenses", 0), "BRL")),
    ]
    kpi_html = "".join(
        "<div class='open-finance-kpi'>"
        f"<span>{html.escape(label)}</span>"
        f"<strong>{html.escape(value)}</strong>"
        "</div>"
        for label, value in kpis
    )
    account_rows = "".join(
        "<tr>"
        f"<td>{pluggy_bank_cell_html(item.get('institution', '-'))}</td>"
        f"<td>{html.escape(item.get('name', '-'))}<span>{html.escape(item.get('number') or '')}</span></td>"
        f"<td class='{pluggy_negative_amount_class(item.get('balance'))}'>{html.escape(format_pluggy_money(item.get('balance'), item.get('currency')))}</td>"
        "</tr>"
        for item in bank_accounts[:6]
    ) or "<tr><td colspan='3' class='muted'>Sem contas correntes retornadas.</td></tr>"
    card_rows = "".join(
        "<tr>"
        f"<td>{pluggy_bank_cell_html(item.get('institution', '-'))}</td>"
        f"<td>{html.escape(clip_action_text(item.get('name', '-'), 25))}"
        f"<span>{html.escape(item.get('number') or '')} | Disp. {html.escape(format_pluggy_money(item.get('available_credit'), item.get('currency')))}</span></td>"
        f"<td>{html.escape(format_pluggy_money(item.get('balance'), item.get('currency')))}</td>"
        f"<td>{html.escape(format_short_date(item.get('due_date')) if item.get('due_date') else '-')}</td>"
        "</tr>"
        for item in credit_cards[:6]
    ) or "<tr><td colspan='4' class='muted'>Sem cartoes retornados.</td></tr>"
    investment_rows = "".join(
        "<tr>"
        f"<td>{pluggy_bank_cell_html(item.get('institution', '-'))}</td>"
        f"<td>{html.escape(clip_action_text(item.get('name', '-'), 24))}"
        f"<span>{html.escape(pluggy_investment_type_label(item.get('type')))}</span></td>"
        f"<td>{html.escape(format_pluggy_money(item.get('value'), item.get('currency')))}</td>"
        "</tr>"
        for item in investments[:7]
    ) or "<tr><td colspan='3' class='muted'>Sem investimentos ativos.</td></tr>"
    expense_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item.get('category') or 'Outros')}</td>"
        f"<td>{html.escape(format_pluggy_money(item.get('past'), 'BRL'))}</td>"
        f"<td>{html.escape(format_pluggy_money(item.get('future'), 'BRL'))}</td>"
        f"<td>{html.escape(format_pluggy_money((item.get('past') or 0) + (item.get('future') or 0), 'BRL'))}</td>"
        "</tr>"
        for item in expense_categories
    ) or "<tr><td colspan='4' class='muted'>Sem despesas categorizadas.</td></tr>"
    warnings = ""
    if snapshot.get("errors"):
        warnings = f"<div class='open-finance-warning'>Avisos: {html.escape('; '.join(snapshot['errors'][:2]))}</div>"
    return (
        "<div class='open-finance-card'>"
        f"<div class='open-finance-kpis'>{kpi_html}</div>"
        "<div class='open-finance-products'>"
        "<div class='open-finance-pane'>"
        "<div class='open-finance-subtitle'>Contas correntes</div>"
        "<table class='open-finance-table open-finance-accounts'>"
        "<thead><tr><th>Banco</th><th>Conta</th><th>Saldo</th></tr></thead>"
        f"<tbody>{account_rows}</tbody>"
        "</table>"
        "</div>"
        "<div class='open-finance-pane'>"
        "<div class='open-finance-subtitle'>Cartoes de credito</div>"
        "<table class='open-finance-table open-finance-cards'>"
        "<thead><tr><th>Banco</th><th>Cartao</th><th>Fatura</th><th>Vence</th></tr></thead>"
        f"<tbody>{card_rows}</tbody>"
        "</table>"
        "</div>"
        "</div>"
        "<div class='open-finance-products open-finance-products-bottom'>"
        "<div class='open-finance-pane'>"
        "<div class='open-finance-subtitle'>Investimentos</div>"
        "<table class='open-finance-table open-finance-investments'>"
        "<thead><tr><th>Banco</th><th>Ativo</th><th>Valor de mercado</th></tr></thead>"
        f"<tbody>{investment_rows}</tbody>"
        "</table>"
        "</div>"
        "<div class='open-finance-pane'>"
        "<div class='open-finance-subtitle'>Despesas por categoria</div>"
        "<table class='open-finance-table open-finance-expenses'>"
        "<thead><tr><th>Categoria</th><th>Passadas 30d</th><th>Futuras</th><th>Total</th></tr></thead>"
        f"<tbody>{expense_rows}</tbody>"
        "</table>"
        "</div>"
        "</div>"
        f"{warnings}"
        "</div>"
    )


def render_pluggy_recent_statements_html(snapshot, days=2, max_rows_per_bank=28):
    today = dt.datetime.now(TIMEZONE).date()
    days = max(1, int(days))
    start_date = today - dt.timedelta(days=days - 1)
    period = f"{start_date.strftime('%d/%m/%Y')} a {today.strftime('%d/%m/%Y')} | Contas correntes via Pluggy"

    if not snapshot.get("configured"):
        error = snapshot.get("error", "Pluggy nao configurado")
        return (
            f"<div class='statement-period'>{html.escape(period)}</div>"
            "<div class='open-finance-card open-finance-empty'>"
            f"<div class='muted'>Extratos indisponiveis: {html.escape(error)}.</div>"
            "</div>"
        )
    if not snapshot.get("available"):
        error = snapshot.get("error", "sem dados retornados")
        return (
            f"<div class='statement-period'>{html.escape(period)}</div>"
            "<div class='open-finance-card open-finance-empty'>"
            f"<div class='muted'>Pluggy conectado, mas sem extratos para exibir: {html.escape(error)}.</div>"
            "</div>"
        )

    bank_order = ("BTG Pactual", "Itau", "Santander")
    rows_by_bank = {bank: [] for bank in bank_order}
    for row in snapshot.get("transactions") or []:
        if str(row.get("account_type") or "").upper() != "BANK":
            continue
        if not pluggy_date_in_recent_calendar_days(row.get("date"), days):
            continue
        bank = pluggy_bank_display_name(row.get("institution"))
        if bank in rows_by_bank:
            rows_by_bank[bank].append(row)

    balances_by_bank = {bank: 0.0 for bank in bank_order}
    for account in snapshot.get("bank_accounts") or []:
        bank = pluggy_bank_display_name(account.get("institution"))
        if bank in balances_by_bank and (account.get("currency") or "BRL") == "BRL":
            balances_by_bank[bank] += pluggy_amount(account.get("balance")) or 0

    bank_cards = []
    for bank in bank_order:
        rows = sorted(
            rows_by_bank[bank],
            key=lambda row: (row.get("date") or "", abs(pluggy_amount(row.get("amount")) or 0)),
            reverse=True,
        )
        income = sum(pluggy_amount(row.get("amount")) or 0 for row in rows if (pluggy_amount(row.get("amount")) or 0) > 0)
        outflow = sum(abs(pluggy_amount(row.get("amount")) or 0) for row in rows if (pluggy_amount(row.get("amount")) or 0) < 0)
        visible_rows = rows[:max_rows_per_bank]
        transaction_html = []
        current_date = None
        for row in visible_rows:
            row_date = str(row.get("date") or "")[:10]
            if row_date != current_date:
                current_date = row_date
                transaction_html.append(
                    f"<div class='statement-date'>{html.escape(statement_date_label(row_date, today))}</div>"
                )
            amount = pluggy_amount(row.get("amount")) or 0
            status = str(row.get("status") or "").upper()
            meta_parts = [clip_action_text(row.get("account") or "Conta", 25)]
            if status == "PENDING":
                meta_parts.append("Pendente")
            meta = " | ".join(meta_parts)
            transaction_html.append(
                "<div class='statement-row'>"
                "<div>"
                f"<div class='statement-description' title='{html.escape(row.get('description') or 'Transacao')}'>"
                f"{html.escape(clip_action_text(row.get('description') or 'Transacao', 42))}</div>"
                f"<div class='statement-meta'>{html.escape(meta)}</div>"
                "</div>"
                f"<div class='statement-amount {pluggy_amount_class(amount)}'>{html.escape(format_pluggy_money(amount, row.get('currency')))}</div>"
                "</div>"
            )
        if not transaction_html:
            transaction_html.append("<div class='statement-empty'>Sem movimentacoes no periodo.</div>")
        if len(rows) > len(visible_rows):
            transaction_html.append(
                f"<div class='statement-overflow'>+ {len(rows) - len(visible_rows)} movimentacoes adicionais no periodo.</div>"
            )

        balance = balances_by_bank[bank]
        bank_cards.append(
            "<div class='statement-bank'>"
            "<div class='statement-bank-head'>"
            "<div class='statement-bank-identity'>"
            f"<span class='statement-bank-logo'>{pluggy_bank_logo_svg(bank)}</span>"
            "<div>"
            f"<div class='statement-bank-name'>{html.escape(bank)}</div>"
            f"<div class='statement-bank-count'>{len(rows)} movimentacoes no periodo</div>"
            "</div>"
            "</div>"
            "<div class='statement-bank-kpis'>"
            "<div class='statement-bank-kpi income'><span>Entradas</span>"
            f"<strong class='money-positive'>{html.escape(format_pluggy_money(income, 'BRL'))}</strong></div>"
            "<div class='statement-bank-kpi outflow'><span>Saidas</span>"
            f"<strong class='money-negative'>{html.escape(format_pluggy_money(outflow, 'BRL'))}</strong></div>"
            "<div class='statement-bank-kpi balance'><span>Saldo atual</span>"
            f"<strong class='{pluggy_negative_amount_class(balance)}'>{html.escape(format_pluggy_money(balance, 'BRL'))}</strong></div>"
            "</div>"
            "</div>"
            f"{''.join(transaction_html)}"
            "</div>"
        )

    warning = ""
    if snapshot.get("errors"):
        warning = "<div class='statement-warning'>Algumas fontes retornaram avisos; os dados disponiveis foram mantidos.</div>"
    return (
        f"<div class='statement-period'>{html.escape(period)}</div>"
        f"<div class='statement-grid'>{''.join(bank_cards)}</div>"
        f"{warning}"
    )


def pluggy_date_in_recent_calendar_days(value, days):
    try:
        row_date = dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return False
    today = dt.datetime.now(TIMEZONE).date()
    start_date = today - dt.timedelta(days=max(1, int(days)) - 1)
    return start_date <= row_date <= today


def statement_date_label(value, today):
    try:
        row_date = dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return format_short_date(value)
    if row_date == today:
        return f"Hoje | {row_date.strftime('%d/%m')}"
    if row_date == today - dt.timedelta(days=1):
        return f"Ontem | {row_date.strftime('%d/%m')}"
    return row_date.strftime("%d/%m/%Y")


def pluggy_bank_cell_html(institution):
    name = pluggy_bank_display_name(institution)
    return (
        "<span class='open-finance-bank'>"
        f"<span class='open-finance-bank-logo'>{pluggy_bank_logo_svg(name)}</span>"
        f"<span class='open-finance-bank-name'>{html.escape(name)}</span>"
        "</span>"
    )


def pluggy_bank_display_name(institution):
    value = normalize_ws(str(institution or "-"))
    lowered = value.lower()
    if "santander" in lowered:
        return "Santander"
    if "itau" in lowered or "itaú" in lowered:
        return "Itau"
    if "btg" in lowered:
        return "BTG Pactual"
    return value or "-"


def pluggy_bank_logo_svg(institution):
    lowered = str(institution or "").lower()
    if "santander" in lowered:
        return """<svg viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg" aria-label="Santander"><rect width="28" height="28" rx="5" fill="#ec0000"/><path d="M14 5c.7 3.1-2.5 4.3-2.1 7 .2 1.6 1.5 2.4 2.4 3.2-3.7-.7-6.4.9-6.4 3.5 0 2.7 2.7 4.7 6.2 4.7s6.2-2 6.2-4.7c0-2.1-1.5-3.7-3.9-4.4 1.7-3.5-1-5.4-2.4-9.3Zm-.1 11.2c2.4 0 4.3 1 4.3 2.4 0 1.4-1.9 2.4-4.3 2.4s-4.3-1-4.3-2.4c0-1.4 1.9-2.4 4.3-2.4Z" fill="#fff"/></svg>"""
    if "itau" in lowered or "itaú" in lowered:
        return """<svg viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg" aria-label="Itau"><rect width="28" height="28" rx="5" fill="#f58220"/><rect x="4" y="5" width="20" height="18" rx="3" fill="#0b2d6b"/><text x="14" y="17.8" text-anchor="middle" font-family="Arial,sans-serif" font-size="8" font-weight="900" fill="#ffd447">ITAU</text></svg>"""
    if "btg" in lowered:
        return """<svg viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg" aria-label="BTG Pactual"><rect width="28" height="28" rx="5" fill="#13294b"/><path d="M6 8h9v4H6zm0 8h16v4H6zm11-8h5v4h-5z" fill="#fff"/></svg>"""
    initial = html.escape((normalize_ws(str(institution or "?")) or "?")[:1].upper())
    return f"""<svg viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg"><rect width="28" height="28" rx="5" fill="#667085"/><text x="14" y="19" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" font-weight="900" fill="#fff">{initial}</text></svg>"""


def pluggy_investment_type_label(value):
    labels = {
        "FIXED_INCOME": "Renda fixa",
        "MUTUAL_FUND": "Fundo",
        "EQUITY": "Acao",
        "ETF": "ETF",
        "SECURITY": "Previdencia",
        "COE": "COE",
    }
    raw = str(value or "-").upper()
    return labels.get(raw, raw.replace("_", " ").title())


def format_pluggy_money(value, currency="BRL"):
    if value is None:
        return "N/D"
    currency = currency or "BRL"
    if currency == "BRL":
        return format_brl(float(value))
    return f"{currency} {float(value):,.2f}"


def pluggy_amount_class(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0
    if amount > 0:
        return "money-positive"
    if amount < 0:
        return "money-negative"
    return ""


def pluggy_negative_amount_class(value):
    try:
        return "money-negative" if float(value) < 0 else ""
    except (TypeError, ValueError):
        return ""


def format_short_date(value):
    value = normalize_ws(value or "")
    if not value:
        return "-"
    try:
        parsed = dt.date.fromisoformat(value[:10])
        return parsed.strftime("%d/%m")
    except ValueError:
        return value[:10]


def render_cheap_stocks_html(candidate_data=None, groups=None, compact=False):
    candidate_data = candidate_data or {}
    selected_groups = groups or tuple(CHEAP_STOCKS.keys())
    sections = []
    for group in selected_groups:
        items = CHEAP_STOCKS.get(group, [])
        if not items:
            continue
        items = sorted(
            items,
            key=lambda item: candidate_upside_sort_key(candidate_data.get(item["ticker"], {})),
        )
        rows = []
        for item in items:
            ticker = item["ticker"]
            enriched = candidate_data.get(ticker, {})
            if not candidate_render_display_eligible(enriched):
                continue
            price = strip_price_currency(enriched.get("price", "N/D"))
            price_to_buy_in = enriched.get("price_to_buy_in", "N/D")
            daily_change_pct = enriched.get("daily_change_pct")
            multiples = enriched.get("multiples") or item["multiples"]
            consensus = enriched.get("consensus", CANDIDATE_TARGETS.get(ticker, "N/D"))
            model_target = enriched.get("model_target", enriched.get("target", "N/D"))
            upside = enriched.get("upside", "N/D")
            buy_price, buy_analysis = format_candidate_buy_in_parts(
                ticker,
                enriched.get("current_price"),
                enriched.get("target_value"),
                enriched.get("price_context"),
                multiples,
            )
            thesis = compact_candidate_text(ticker, "thesis", item["thesis"]) if compact else item["thesis"]
            risk = compact_candidate_text(ticker, "risk", item["risk"]) if compact else item["risk"]
            rows.append(
                "<tr>"
                f"<td class='candidate-ticker'>{candidate_ticker_cell_html(ticker)}{candidate_status_badge_html(item)}</td>"
                f"<td>{render_candidate_price_html(price, daily_change_pct)}<span class='price-to-buy-in'>{html.escape(price_to_buy_in)} vs buy-in</span></td>"
                f"<td>{render_candidate_multiples_html(multiples)}</td>"
                f"<td>{render_candidate_target_html(consensus, upside, model_target)}</td>"
                f"<td><span class='buy-price'>{html.escape(buy_price)}</span><br><span class='buy-analysis'>{html.escape(buy_analysis)}</span></td>"
                f"<td><span class='thesis-text'>{html.escape(thesis)}</span><br><span class='risk-text'>Risco: {html.escape(risk)}</span></td>"
                "</tr>"
            )
        group_class = re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-")
        if not rows:
            continue
        sections.append(
            f"""
            <div class="candidate-group {html.escape(group_class)}">
              <div class="candidate-group-title">{html.escape(group)}</div>
              <table class="candidate-table">
                <thead><tr><th>COMPANY</th><th>PRICE</th><th>MULTIPLES</th><th>CONSENSUS/TP</th><th>Buy-in Price / AI</th><th>THESIS &amp; RISK</th></tr></thead>
                <tbody>{''.join(rows)}</tbody>
              </table>
            </div>"""
        )
    return "\n".join(sections)


def candidate_render_display_eligible(enriched):
    if not enriched:
        return False
    upside = enriched.get("upside_pct")
    distance = enriched.get("buy_in_distance_pct")
    if upside is None or upside < MIN_CANDIDATE_UPSIDE_PCT:
        return False
    if distance is None:
        return False
    return (
        MIN_CANDIDATE_BUY_IN_DISTANCE_PCT
        <= distance
        < MAX_CANDIDATE_BUY_IN_DISTANCE_PCT
    )


def candidate_status_badge_html(item):
    if item.get("candidate_status") != "Watchlist":
        return ""
    return "<span class='candidate-status-badge'>Watchlist</span>"


def candidate_upside_sort_key(enriched):
    upside = enriched.get("upside_pct")
    if upside is None:
        return (1, 9999)
    return (0, -upside)


def candidate_score_sort_key(item):
    score = item.get("score")
    if score is None:
        return (1, 9999)
    return (0, -score)


def compact_candidate_text(ticker, kind, fallback):
    return shorten_candidate_text(fallback, 128 if kind == "thesis" else 82)


def shorten_candidate_text(value, limit):
    value = normalize_ws(value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip(" ,.;") + "..."


def candidate_ticker_cell_html(ticker):
    yahoo_url = candidate_yahoo_finance_url(ticker)
    name_class = "candidate-name candidate-yahoo-link"
    if CANDIDATE_IS_ETF.get(ticker):
        name_class += " candidate-etf-name"
    return (
        "<div class='candidate-ticker-cell'>"
        f"<span class='candidate-symbol'>{html.escape(ticker)}</span>"
        f"<a class='{name_class}' href='{html.escape(yahoo_url, quote=True)}'>"
        f"{html.escape(candidate_company_name(ticker))}</a>"
        "<span class='candidate-brand-logo'>"
        f"{candidate_logo_svg(ticker)}"
        "</span>"
        "</div>"
    )


def candidate_yahoo_finance_url(ticker):
    symbol = CANDIDATE_SYMBOLS.get(ticker, ticker)
    return f"https://finance.yahoo.com/quote/{urllib.parse.quote(symbol)}"


def render_candidate_price_html(price, daily_change_pct):
    if daily_change_pct is None:
        change_html = ""
    else:
        cls = "pos" if daily_change_pct >= 0 else "neg"
        arrow = "&#9650;" if daily_change_pct >= 0 else "&#9660;"
        change_html = (
            f"<span class='candidate-day-change {cls}'>{arrow} "
            f"{html.escape(format_signed_pct(daily_change_pct))}</span>"
        )
    return (
        "<span class='candidate-price-line'>"
        f"<span class='current-price'>{html.escape(price)}</span>"
        f"{change_html}"
        "</span>"
    )


def candidate_logo_cell_html(ticker):
    return (
        "<span class='candidate-company-logo'>"
        f"{candidate_logo_svg(ticker)}"
        "</span>"
    )


def candidate_company_name(ticker):
    if ticker in CANDIDATE_NAMES:
        return CANDIDATE_NAMES[ticker]
    names = {
        "ABEV3": "Ambev",
        "ALUP11": "Alupar",
        "ASAI3": "Assai",
        "AURE3": "Auren",
        "AZUL4": "Azul",
        "B3SA3": "B3",
        "BBDC3": "Bradesco",
        "BBSE3": "BB Seguridade",
        "BEEF3": "Minerva",
        "BPAC11": "BTG Pactual",
        "BRAP4": "Bradespar",
        "BRAV3": "Brava Energia",
        "BRFS3": "BRF",
        "CCRO3": "CCR",
        "CMIG4": "Cemig",
        "CMIN3": "CSN Mineracao",
        "COGN3": "Cogna",
        "CPFE3": "CPFL Energia",
        "CPLE6": "Copel",
        "CRFB3": "Carrefour Brasil",
        "CSAN3": "Cosan",
        "CSNA3": "CSN",
        "CURY3": "Cury",
        "MRVE3": "MRV",
        "DIRR3": "Direcional",
        "DXCO3": "Dexco",
        "EGIE3": "Engie Brasil",
        "ELET3": "Eletrobras",
        "ELET6": "Eletrobras",
        "EMBR3": "Embraer",
        "ENEV3": "Eneva",
        "EQTL3": "Equatorial",
        "EZTC3": "EZTec",
        "FLRY3": "Fleury",
        "GGBR4": "Gerdau",
        "GMAT3": "Grupo Mateus",
        "GOAU4": "Metalurgica Gerdau",
        "HAPV3": "Hapvida",
        "HYPE3": "Hypera",
        "IGTI11": "Iguatemi",
        "ITSA4": "Itausa",
        "YDUQ3": "Yduqs",
        "CYRE3": "Cyrela",
        "TOTS3": "Totvs",
        "PETR3": "Petrobras",
        "PETR4": "Petrobras",
        "VALE3": "Vale",
        "BBAS3": "Banco do Brasil",
        "ITUB4": "Itau",
        "BBDC4": "Bradesco",
        "JBSS3": "JBS",
        "KLBN11": "Klabin",
        "WEGE3": "WEG",
        "LWSA3": "LWSA",
        "MGLU3": "Magazine Luiza",
        "MRFG3": "Marfrig",
        "MULT3": "Multiplan",
        "NTCO3": "Natura",
        "ONCO3": "Oncoclinicas",
        "PCAR3": "Pao de Acucar",
        "PETZ3": "Petz",
        "POMO4": "Marcopolo",
        "PRIO3": "PRIO",
        "PSSA3": "Porto",
        "RADL3": "Raia Drogasil",
        "RAIL3": "Rumo",
        "RAIZ4": "Raizen",
        "RDOR3": "Rede D'Or",
        "RECV3": "PetroReconcavo",
        "RENT3": "Localiza",
        "SANB11": "Santander Brasil",
        "SBSP3": "Sabesp",
        "SLCE3": "SLC Agricola",
        "SMTO3": "Sao Martinho",
        "SUZB3": "Suzano",
        "TAEE11": "Taesa",
        "TIMS3": "TIM",
        "UGPA3": "Ultrapar",
        "USIM5": "Usiminas",
        "VBBR3": "Vibra",
        "VIVA3": "Vivara",
        "VIVT3": "Vivo",
        "LREN3": "Renner",
        "CHTR": "Charter",
        "PDD": "PDD",
        "TCOM": "Trip.com",
        "ADBE": "Adobe",
        "JD": "JD.com",
        "PYPL": "PayPal",
        "GOOGL": "Alphabet",
        "META": "Meta",
        "QCOM": "Qualcomm",
        "MU": "Micron",
        "INTC": "Intel",
        "GILD": "Gilead",
        "CSCO": "Cisco",
        "TME": "Tencent Music",
        "TAL": "TAL Education",
        "FUTU": "Futu",
        "BABA": "Alibaba",
        "CRM": "Salesforce",
        "CHWY": "Chewy",
        "BILL": "BILL",
        "RBLX": "Roblox",
        "FMC": "FMC",
        "DIS": "Disney",
        "NKE": "Nike",
        "BMY": "Bristol Myers",
        "PFE": "Pfizer",
        "CVS": "CVS Health",
        "VZ": "Verizon",
        "C": "Citi",
        "OXY": "Occidental",
        "IBIT": "iShares Bitcoin Trust",
        "QQQ": "Invesco QQQ",
        "SMH": "VanEck Semiconductor",
        "SOXX": "iShares Semiconductor",
        "CIBR": "First Trust Cybersecurity",
        "ICLN": "iShares Clean Energy",
        "KWEB": "KraneShares China Internet",
        "ARKF": "ARK Fintech Innovation",
        "FINX": "Global X FinTech",
        "BKCH": "Global X Blockchain",
        "GDX": "VanEck Gold Miners",
        "GDXJ": "VanEck Junior Gold Miners",
        "SLV": "iShares Silver Trust",
        "ARKK": "ARK Innovation",
    }
    return names.get(ticker, ticker)


def candidate_brand_wordmark_name(ticker):
    explicit = {
        "IBIT": "iShares",
        "QQQ": "Invesco QQQ",
        "SMH": "VanEck",
        "SOXX": "iShares",
        "CIBR": "First Trust",
        "ICLN": "iShares",
        "KWEB": "KraneShares",
        "ARKF": "ARK",
        "FINX": "Global X",
        "BKCH": "Global X",
        "GDX": "VanEck",
        "GDXJ": "VanEck",
        "SLV": "iShares",
        "ARKK": "ARK",
    }
    if ticker in explicit:
        return explicit[ticker]
    name = candidate_company_name(ticker)
    name = re.sub(
        r"\b(incorporated|inc\.?|corp\.?|corporation|company|co\.?|ltd\.?|limited|plc|s\.a\.?|sa|class\s+[a-z])\b",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = normalize_ws(re.sub(r"[,.;]+", " ", name)).strip(" -")
    if len(name) <= 18:
        return name or ticker
    words = name.split()
    for count in range(min(2, len(words)), 0, -1):
        candidate = " ".join(words[:count])
        if len(candidate) <= 18:
            return candidate
    return words[0][:18] if words else ticker


def candidate_logo_svg(ticker):
    logos = {
        "COGN3": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Cogna">
  <circle cx="18" cy="20" r="13" fill="#6b2fb3"/>
  <text x="12" y="26" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="900" fill="#ffffff">C</text>
  <text x="38" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="900" fill="#6b2fb3">Cogna</text>
</svg>""",
        "MRVE3": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="MRV">
  <rect x="3" y="9" width="30" height="22" rx="4" fill="#009739"/>
  <path d="M10 25 L18 14 L26 25" fill="none" stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="900" fill="#009739">MRV</text>
</svg>""",
        "YDUQ3": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Yduqs">
  <path d="M18 5 L32 13 V24 C32 31 26 35 18 37 C10 35 4 31 4 24 V13 Z" fill="#004b93"/>
  <text x="12" y="26" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="900" fill="#ffffff">Y</text>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="900" fill="#004b93">Yduqs</text>
</svg>""",
        "CYRE3": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Cyrela">
  <circle cx="18" cy="20" r="13" fill="#8a6f2a"/>
  <path d="M24 13 C16 8 9 14 10 21 C11 29 20 31 26 25" fill="none" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/>
  <text x="39" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="900" fill="#8a6f2a">Cyrela</text>
</svg>""",
        "TOTS3": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="TOTVS">
  <rect x="3" y="10" width="31" height="20" rx="10" fill="#0057ff"/>
  <circle cx="18" cy="20" r="5" fill="#ffffff"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="900" fill="#0057ff">TOTVS</text>
</svg>""",
        "RAIL3": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Rumo">
  <rect x="3" y="11" width="30" height="18" rx="3" fill="#f97316"/>
  <path d="M10 25 L16 15 H25" fill="none" stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="900" fill="#f97316">Rumo</text>
</svg>""",
        "IBIT": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="iShares">
  <circle cx="17" cy="20" r="13" fill="#111827"/>
  <circle cx="17" cy="20" r="8" fill="#f7931a"/>
  <text x="13" y="25" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="900" fill="#ffffff">B</text>
  <text x="38" y="25" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="900" fill="#111827">iShares</text>
</svg>""",
        "CRMD": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="CorMedix">
  <rect x="4" y="12" width="28" height="16" rx="8" fill="#0ea5e9"/>
  <circle cx="15" cy="20" r="5" fill="#ffffff"/>
  <text x="39" y="25" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="900" fill="#0369a1">CorMedix</text>
</svg>""",
        "TASK": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="TaskUs">
  <circle cx="18" cy="20" r="13" fill="#6d28d9"/>
  <circle cx="18" cy="20" r="5" fill="#ffffff"/>
  <text x="39" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="900" fill="#6d28d9">TaskUs</text>
</svg>""",
        "CHTR": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Charter">
  <path d="M6 24 C17 8 34 10 38 21" fill="none" stroke="#005daa" stroke-width="5" stroke-linecap="round"/>
  <circle cx="34" cy="21" r="5" fill="#005daa"/>
  <text x="43" y="25" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="900" fill="#005daa">Charter</text>
</svg>""",
        "INVA": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Innoviva">
  <path d="M18 31 C7 20 13 8 31 9 C31 24 25 31 18 31 Z" fill="#16a34a"/>
  <path d="M15 25 C20 20 25 16 31 12" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="900" fill="#15803d">Innoviva</text>
</svg>""",
        "OPFI": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="OppFi">
  <rect x="4" y="8" width="28" height="24" rx="12" fill="#0891b2"/>
  <text x="11" y="26" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="900" fill="#ffffff">O</text>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="900" fill="#0891b2">OppFi</text>
</svg>""",
        "DEC": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Diversified Energy">
  <path d="M18 5 C28 16 31 26 18 35 C5 26 8 16 18 5 Z" fill="#0f766e"/>
  <path d="M13 25 C18 18 22 15 26 12" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="900" fill="#0f766e">Diversified</text>
</svg>""",
        "BRBR": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="BellRing Brands">
  <rect x="4" y="10" width="32" height="20" rx="4" fill="#dc2626"/>
  <circle cx="20" cy="20" r="6" fill="#ffffff"/>
  <text x="44" y="25" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="900" fill="#dc2626">BellRing</text>
</svg>""",
        "HLF": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Herbalife">
  <circle cx="18" cy="20" r="13" fill="#16a34a"/>
  <path d="M10 22 C16 10 24 13 27 22 C21 19 15 19 10 22 Z" fill="#ffffff"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="900" fill="#16a34a">Herbalife</text>
</svg>""",
        "UHS": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Universal Health Services">
  <rect x="4" y="8" width="28" height="24" rx="5" fill="#1e3a8a"/>
  <path d="M18 13 V27 M11 20 H25" stroke="#ffffff" stroke-width="4" stroke-linecap="round"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="900" fill="#1e3a8a">Universal</text>
</svg>""",
    }
    if ticker in logos:
        return logos[ticker]
    return candidate_fallback_logo_svg(ticker)


def candidate_fallback_logo_svg(ticker):
    name = candidate_brand_wordmark_name(ticker)
    color = candidate_logo_color(ticker)
    safe_name = html.escape(shorten_logo_text(name, 13))
    initial_source = re.sub(r"[^A-Za-z0-9]", "", name) or ticker
    initial = html.escape(initial_source[:1].upper())
    return f"""
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="{html.escape(name)}">
  <rect x="4" y="8" width="28" height="24" rx="7" fill="{color}"/>
  <text x="18" y="25" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="900" fill="#ffffff">{initial}</text>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="900" fill="{color}">{safe_name}</text>
</svg>"""


def candidate_logo_color(ticker):
    palette = ["#175cd3", "#7c3aed", "#0f766e", "#b42318", "#8a6f2a", "#0369a1", "#c2410c"]
    return palette[sum(ord(char) for char in ticker) % len(palette)]


def shorten_logo_text(value, limit):
    value = normalize_ws(value)
    return value if len(value) <= limit else value[: max(0, limit - 1)].rstrip() + "."


def render_market_table_row_html(market, include_logo=False, include_crypto_logo=False, include_index_logo=False):
    price = strip_price_currency(format_market_price(market["symbol"], market["price"])) if market.get("price") is not None else "-"
    change = market.get("change")
    pct = market.get("change_pct")
    if change is None or pct is None:
        move = market.get("state") or "indisponivel"
        cls = "muted"
    else:
        move = format_signed_pct(pct)
        cls = "pos" if change >= 0 else "neg"
    when = market["time"].strftime("%H:%M") if market.get("time") else "-"
    logo_cell = render_stock_logo_cell(market) if include_logo or include_crypto_logo or include_index_logo else ""
    if include_logo:
        day_low = strip_price_currency(format_market_price(market["symbol"], market.get("day_low"))) if market.get("day_low") is not None else "-"
        day_high = strip_price_currency(format_market_price(market["symbol"], market.get("day_high"))) if market.get("day_high") is not None else "-"
        return (
            "<tr>"
            f"{logo_cell}"
            f"<td class='asset'>{html.escape(market['label'])}</td>"
            f"<td>{html.escape(price)}</td>"
            f"<td class='{cls}'>{html.escape(move)}</td>"
            f"<td class='muted'>{html.escape(day_low)}</td>"
            f"<td class='muted'>{html.escape(day_high)}</td>"
            "</tr>"
        )
    if include_crypto_logo:
        return (
            "<tr>"
            f"{logo_cell}"
            f"<td class='asset'>{html.escape(market['label'])}</td>"
            f"<td>{html.escape(price)}</td>"
            f"<td class='{cls}'>{html.escape(move)}</td>"
            f"<td class='muted'>{html.escape(when)}</td>"
            "</tr>"
        )
    return (
        "<tr>"
        f"{logo_cell}"
        f"<td class='asset'>{html.escape(market['label'])}</td>"
        f"<td>{html.escape(price)}</td>"
        f"<td class='{cls}'>{html.escape(move)}</td>"
        f"<td class='muted'>{html.escape(when)}</td>"
        "</tr>"
    )


def render_stock_logo_cell(market):
    logo = stock_logo_svg(market["symbol"], market["label"])
    return (
        "<td class='logo-cell'>"
        "<span class='company-logo'>"
        f"{logo}"
        "</span>"
        "</td>"
    )


def stock_logo_svg(symbol, label):
    logos = {
        "ES=F": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="S&amp;P 500">
  <rect x="3" y="8" width="31" height="24" rx="4" fill="#0f5da8"/>
  <text x="9" y="25" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="900" fill="#ffffff">S&amp;P</text>
  <text x="42" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="850" fill="#111827">500</text>
</svg>""",
        "NQ=F": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Nasdaq">
  <path d="M8 29 L19 8 L31 29 H23 L18 18 L13 29 Z" fill="#0090d8"/>
  <text x="39" y="25" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="850" fill="#111827">Nasdaq</text>
</svg>""",
        "^N225": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Nikkei">
  <circle cx="18" cy="20" r="13" fill="#bc002d"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="850" fill="#111827">Nikkei</text>
</svg>""",
        "^GDAXI": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="DAX">
  <rect x="3" y="8" width="31" height="24" rx="4" fill="#111827"/>
  <path d="M10 25 L17 15 L23 21 L29 12" fill="none" stroke="#f6c453" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="42" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="850" fill="#111827">DAX</text>
</svg>""",
        "000001.SS": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Shanghai Composite">
  <rect x="3" y="8" width="31" height="24" rx="4" fill="#b42318"/>
  <path d="M10 25 H27 M13 20 H24 M16 15 H21" stroke="#f6c453" stroke-width="2.3" stroke-linecap="round"/>
  <text x="39" y="18" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="850" fill="#111827">Shanghai</text>
  <text x="39" y="30" font-family="Arial, Helvetica, sans-serif" font-size="10" font-weight="800" fill="#52616f">Composite</text>
</svg>""",
        "BTC-USD": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Bitcoin">
  <circle cx="18" cy="20" r="13" fill="#f7931a"/>
  <text x="13" y="27" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="900" fill="#ffffff">₿</text>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="800" fill="#111827">BTC</text>
</svg>""",
        "ETH-USD": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Ethereum">
  <polygon points="18,4 8,21 18,16 28,21" fill="#627eea"/>
  <polygon points="18,18 8,23 18,36 28,23" fill="#8fa2ff"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="800" fill="#111827">ETH</text>
</svg>""",
        "SOL-USD": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Solana">
  <rect x="5" y="8" width="27" height="6" rx="2" fill="#14f195"/>
  <rect x="5" y="17" width="27" height="6" rx="2" fill="#9945ff"/>
  <rect x="5" y="26" width="27" height="6" rx="2" fill="#14f195"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="800" fill="#111827">SOL</text>
</svg>""",
        "BONK-USD": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Bonk">
  <circle cx="18" cy="20" r="13" fill="#f97316"/>
  <path d="M10 15 L14 9 L18 15 L22 9 L26 15" fill="#fff2cc"/>
  <circle cx="14" cy="20" r="2" fill="#111827"/>
  <circle cx="22" cy="20" r="2" fill="#111827"/>
  <path d="M15 26 Q18 29 22 26" fill="none" stroke="#111827" stroke-width="2" stroke-linecap="round"/>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="800" fill="#111827">BONK</text>
</svg>""",
        "DOGE-USD": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Dogecoin">
  <circle cx="18" cy="20" r="13" fill="#c2a633"/>
  <text x="12" y="27" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="900" fill="#ffffff">Ð</text>
  <text x="40" y="25" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="800" fill="#111827">DOGE</text>
</svg>""",
        "AMZN": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Amazon">
  <text x="2" y="20" font-family="Arial, Helvetica, sans-serif" font-size="19" font-weight="700" fill="#111827">amazon</text>
  <path d="M30 28 C48 37, 70 35, 88 24" fill="none" stroke="#f59e0b" stroke-width="4" stroke-linecap="round"/>
  <path d="M84 23 L95 22 L88 30" fill="none" stroke="#f59e0b" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>""",
        "AVGO": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Broadcom">
  <path d="M4 11 H56 C66 11, 72 16, 72 23 C72 30, 66 34, 56 34 H4 Z" fill="#cc092f"/>
  <text x="12" y="28" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="900" fill="#ffffff">B</text>
  <text x="42" y="26" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="900" fill="#111827">Broadcom</text>
</svg>""",
        "VOO": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Vanguard">
  <path d="M10 6 L20 30 L30 6" fill="none" stroke="#b42318" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="38" y="25" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="700" fill="#111827">Vanguard</text>
</svg>""",
        "TTWO": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Take-Two Interactive">
  <text x="4" y="23" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="900" fill="#111827">TAKE</text>
  <text x="46" y="23" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="900" fill="#175cd3">TWO</text>
  <path d="M5 29 H88" stroke="#175cd3" stroke-width="2.5" stroke-linecap="round"/>
</svg>""",
        "SPCX": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="SPCX">
  <rect x="2" y="8" width="26" height="24" rx="4" fill="#111827"/>
  <text x="8" y="26" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="800" fill="#ffffff">S</text>
  <text x="34" y="25" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="800" fill="#111827">SPCX</text>
</svg>""",
        "KWEB": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="KraneShares">
  <path d="M9 29 L19 8 L29 29 Z" fill="#b42318"/>
  <path d="M18 18 L31 8 L25 23" fill="#f97316"/>
  <text x="38" y="18" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="800" fill="#111827">Krane</text>
  <text x="38" y="30" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="800" fill="#111827">Shares</text>
</svg>""",
        "MHVYF": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Mitsubishi Heavy Industries">
  <polygon points="18,3 27,17 18,25 9,17" fill="#e60012"/>
  <polygon points="8,18 17,26 14,37 1,26" fill="#e60012"/>
  <polygon points="28,18 35,26 22,37 19,26" fill="#e60012"/>
  <text x="40" y="18" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="800" fill="#111827">Mitsubishi</text>
  <text x="40" y="30" font-family="Arial, Helvetica, sans-serif" font-size="10" font-weight="700" fill="#52616f">Heavy</text>
</svg>""",
        "UNIP6.SA": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Unipar">
  <circle cx="18" cy="20" r="12" fill="#175cd3"/>
  <path d="M11 15 C16 23, 21 23, 26 15" fill="none" stroke="#ffffff" stroke-width="4" stroke-linecap="round"/>
  <text x="36" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="800" fill="#111827">Unipar</text>
</svg>""",
        "PRNR3.SA": """
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="Priner">
  <rect x="3" y="9" width="25" height="22" rx="3" fill="#0b4f6c"/>
  <path d="M10 25 L16 14 L23 25" fill="none" stroke="#f6c453" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="35" y="25" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="800" fill="#111827">Priner</text>
</svg>""",
    }
    if symbol in logos:
        return logos[symbol]
    initials = html.escape(label[:3].upper())
    return f"""
<svg viewBox="0 0 108 40" xmlns="http://www.w3.org/2000/svg" aria-label="{html.escape(label)}">
  <rect x="2" y="8" width="44" height="24" rx="4" fill="#eef2f6"/>
  <text x="10" y="25" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="800" fill="#52616f">{initials}</text>
</svg>"""


def render_billfish_panel_html(billfish):
    if not billfish.get("available"):
        return f"<div class='empty'>Billfish FIA indisponivel: {html.escape(billfish.get('error', 'sem detalhe'))}</div>"
    latest = billfish["latest"]
    ret = latest.get("daily_return_pct")
    pl_change = latest.get("pl_change")
    ret_cls = "pos" if ret is not None and ret >= 0 else "neg"
    pl_cls = "pos" if pl_change is not None and pl_change >= 0 else "neg"
    performance = billfish.get("performance") or {}
    perf_rows = ""
    for label, month_key, year_key in [
        ("Billfish FIA", "billfish_month_pct", "billfish_year_pct"),
        ("Ibovespa", "ibov_month_pct", "ibov_year_pct"),
        ("S&P 500", "sp500_month_pct", "sp500_year_pct"),
        ("CDI", "cdi_month_pct", "cdi_year_pct"),
        ("IPCA 12M", None, "ipca_12m_pct"),
    ]:
        month = performance.get(month_key) if month_key else None
        year = performance.get(year_key)
        month_cls = "pos" if month is not None and month >= 0 else "neg"
        year_cls = "pos" if year is not None and year >= 0 else "neg"
        perf_rows += (
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td class='{month_cls}'>{html.escape(format_optional_pct(month) if month_key else '-')}</td>"
            f"<td class='{year_cls}'>{html.escape(format_optional_pct(year))}</td>"
            "</tr>"
        )
    return f"""
    <div class="billfish">
      <div class="bill-main">
        <h3>STATUS {html.escape(latest['date'])}</h3>
        <div class="bill-meta">Fonte: {html.escape(billfish.get('source', latest.get('source', '')))}</div>
        <div class="bill-kpis">
          <div class="kpi"><div class="kpi-label">Daily change</div><div class="kpi-value {ret_cls}">{html.escape(format_pct(ret)) if ret is not None else 'N/D'}</div></div>
          <div class="kpi"><div class="kpi-label">Net worth</div><div class="kpi-value">{html.escape(format_brl(latest['pl']))}</div></div>
          <div class="kpi"><div class="kpi-label">Net worth change</div><div class="kpi-value {pl_cls}">{html.escape(format_brl_signed(pl_change))}</div></div>
          <div class="kpi"><div class="kpi-label">Quota</div><div class="kpi-value">{html.escape(f"{latest.get('quota'):.8f}" if latest.get('quota') else 'N/D')}</div></div>
        </div>
      </div>
      <div class="perf">
        <div class="perf-title">PROFITABILITY</div>
        <table>
          <thead><tr><th>Index</th><th>Month</th><th>Year</th></tr></thead>
          <tbody>{perf_rows}</tbody>
        </table>
      </div>
    </div>"""


def render_brokerage_notes_panel_html(snapshot):
    if not snapshot.get("available"):
        return f"<div class='empty'>Notas de corretagem indisponiveis: {html.escape(snapshot.get('error', 'sem detalhe'))}</div>"
    trades = snapshot.get("trades") or []
    rows = []
    for trade in trades:
        quantity = f"{trade.get('quantity'):,}".replace(",", ".") if trade.get("quantity") is not None else "-"
        price = trade.get("price")
        if isinstance(price, (int, float)):
            price_text = format_brl(price)
        else:
            price_text = str(price or "-")
        value = format_brl(trade["value"]) if trade.get("value") is not None else "-"
        net = format_brl_signed(trade["net"]) if trade.get("net") is not None else "-"
        rows.append(
            "<tr>"
            f"<td>{html.escape(trade.get('type', '-'))}</td>"
            f"<td>{html.escape(trade.get('side', '-'))}</td>"
            f"<td><span class='brokerage-asset'>{html.escape(trade.get('asset', '-'))}</span></td>"
            f"<td>{html.escape(quantity)}</td>"
            f"<td>{html.escape(price_text)}</td>"
            f"<td>{html.escape(value)}</td>"
            f"<td>{html.escape(net)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='7' class='muted'>Nenhuma operacao parseada no anexo.</td></tr>")
    note_types = ", ".join(snapshot.get("note_types") or ["Nota"])
    financial_summary = render_brokerage_financial_summary_html(snapshot.get("financial_summary") or [])
    return f"""
    <div class="brokerage-notes">
      <div class="brokerage-summary">
        <div class="brokerage-kpi"><div class="brokerage-kpi-label">Trade date</div><div class="brokerage-kpi-value">{html.escape(snapshot.get('trade_date') or '-')}</div></div>
        <div class="brokerage-kpi"><div class="brokerage-kpi-label">Type</div><div class="brokerage-kpi-value">{html.escape(note_types)}</div></div>
        <div class="brokerage-kpi"><div class="brokerage-kpi-label">Total traded</div><div class="brokerage-kpi-value">{html.escape(format_brl(snapshot.get('total_traded') or 0))}</div></div>
        <div class="brokerage-kpi"><div class="brokerage-kpi-label">Net total</div><div class="brokerage-kpi-value">{html.escape(format_brl_signed(snapshot.get('net_total') or 0))}</div></div>
      </div>
      <table class="brokerage-table">
        <thead><tr><th>Type</th><th>Side</th><th>Asset</th><th>Qty</th><th>Price/Rate</th><th>Value</th><th>Net</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      {financial_summary}
    </div>"""


def render_brokerage_financial_summary_html(items):
    if not items:
        return ""
    chips = []
    for item in items:
        value = item.get("value")
        if value is None:
            continue
        cls = "pos" if value >= 0 else "neg"
        value_text = format_brl_signed(value) if item.get("signed") else format_brl(value)
        chips.append(
            "<span class='brokerage-financial-chip'>"
            f"<span>{html.escape(item.get('label', '-'))}</span>"
            f"<strong class='{cls}'>{html.escape(value_text)}</strong>"
            "</span>"
        )
    if not chips:
        return ""
    return (
        "<div class='brokerage-financial'>"
        "<div class='brokerage-financial-title'>Financial Summary</div>"
        "<div class='brokerage-financial-grid'>"
        + "".join(chips)
        + "</div></div>"
    )


def render_event_card_html(event):
    if event["all_day"]:
        when = "Dia inteiro"
    elif event["start"] and event["end"]:
        when = f"{event['start'].strftime('%H:%M')} - {event['end'].strftime('%H:%M')}"
    else:
        when = "Horario nao disponivel"
    location = event["location"] or "-"
    return (
        "<div class='card'>"
        f"<div class='card-head'><div class='card-title'>{html.escape(when)}</div><span class='muted'>{html.escape(location)}</span></div>"
        f"<div>{html.escape(event['subject'])}</div>"
        "</div>"
    )


def render_forecast_panel_html(forecast):
    if not forecast.get("available"):
        error = forecast.get("error", "previsao indisponivel")
        return f"<div class='empty'>Forecast indisponivel: {html.escape(error)}.</div>"
    chart_locations = forecast.get("chart_locations") or []
    summary_locations = forecast.get("summary_locations") or []
    if chart_locations or summary_locations:
        charts = "".join(render_forecast_city_card_html(item, compact=True) for item in chart_locations)
        summary = render_forecast_summary_table_html(summary_locations)
        warnings = ""
        if forecast.get("errors"):
            warnings = f"<div class='muted'>Alguns locais indisponiveis: {html.escape('; '.join(forecast['errors']))}</div>"
        return f"<div class='forecast-grid'>{charts}</div>{summary}{warnings}"
    return render_forecast_city_card_html(forecast)


def render_forecast_city_card_html(forecast, compact=False):
    location = forecast.get("location", {})
    place_parts = [location.get("city"), location.get("region"), location.get("country")]
    place = forecast.get("label") or ", ".join(part for part in place_parts if part) or "Local atual"
    meta_parts = [f"Sensacao {format_temp_pair(forecast.get('feels_c'))}"]
    wind = forecast.get("wind_kmh")
    rain = forecast.get("precipitation_mm")
    if wind is not None:
        meta_parts.append(f"Vento {format_forecast_wind(wind, forecast.get('wind_direction_deg'))}")
    if rain is not None:
        meta_parts.append(f"Chuva {rain:.1f} mm")
    hourly_chart = render_hourly_forecast_chart_html(forecast.get("hourly", []))

    day_cards = []
    for idx, day in enumerate(forecast.get("days", [])[:3]):
        rain_pct = day.get("rain_pct")
        rain_text = f"Prob. {rain_pct:.0f}%" if rain_pct is not None else "Prob. -"
        day_cards.append(
            "<div class='forecast-day'>"
            f"<div class='forecast-date'>{html.escape(forecast_day_label(day.get('date'), idx))}</div>"
            f"<div class='forecast-range'>{html.escape(format_temp_c(day.get('low_c')))} - {html.escape(format_temp_c(day.get('high_c')))}</div>"
            f"<div class='forecast-rain'>{html.escape(weather_code_label(day.get('code')))} | {html.escape(rain_text)}</div>"
            "</div>"
        )

    return (
        "<div class='forecast-box'>"
        "<div class='forecast-main'>"
        "<div class='forecast-place'>"
        f"<div class='forecast-condition-icon'>{weather_condition_icon_html(forecast.get('weather_code'))}</div>"
        "<div>"
        f"<div class='forecast-location'>{html.escape(place)}</div>"
        f"<div class='forecast-desc'>{html.escape(weather_code_label(forecast.get('weather_code')))}</div>"
        "</div>"
        "</div>"
        "<div>"
        f"<div class='forecast-temp'>{html.escape(format_temp_pair(forecast.get('temperature_c')))}</div>"
        f"<div class='forecast-meta'>{html.escape(' | '.join(meta_parts))}</div>"
        "</div>"
        "</div>"
        f"{hourly_chart}"
        f"<div class='forecast-days'>{''.join(day_cards)}</div>"
        "</div>"
    )


def render_forecast_summary_table_html(items):
    if not items:
        return ""
    cards = []
    for item in items:
        place = item.get("label") or item.get("location", {}).get("city", "-")
        condition = weather_code_label(item.get("weather_code"))
        cards.append(
            "<div class='forecast-summary-card'>"
            f"<div class='forecast-summary-icon'>{weather_condition_icon_html(item.get('weather_code'))}</div>"
            "<div>"
            f"<div class='forecast-summary-place'>{html.escape(place)}</div>"
            f"<div class='forecast-summary-condition'>{html.escape(condition)}</div>"
            "<div class='forecast-summary-metrics'>"
            "<div class='forecast-summary-metric'>"
            "<span>Temp.</span>"
            f"<strong>{html.escape(format_temp_pair(item.get('temperature_c')))}</strong>"
            "</div>"
            "<div class='forecast-summary-metric'>"
            "<span>Chuva</span>"
            f"<strong>{html.escape(format_forecast_rain_mm(item.get('precipitation_mm')))}</strong>"
            "</div>"
            "<div class='forecast-summary-metric'>"
            "<span>Vento</span>"
            f"<strong>{html.escape(format_forecast_wind(item.get('wind_kmh'), item.get('wind_direction_deg')))}</strong>"
            "</div>"
            "</div>"
            "</div>"
            "</div>"
        )
    return f"<div class='forecast-summary-grid'>{''.join(cards)}</div>"


def weather_condition_icon_html(code):
    try:
        weather_code = int(code)
    except (TypeError, ValueError):
        weather_code = None
    if weather_code == 0:
        return """
        <svg viewBox="0 0 64 64" role="img" aria-label="Clear">
          <circle cx="32" cy="32" r="13" fill="#f6c445"/>
          <g stroke="#f6c445" stroke-width="5" stroke-linecap="round">
            <line x1="32" y1="5" x2="32" y2="14"/>
            <line x1="32" y1="50" x2="32" y2="59"/>
            <line x1="5" y1="32" x2="14" y2="32"/>
            <line x1="50" y1="32" x2="59" y2="32"/>
            <line x1="13" y1="13" x2="19" y2="19"/>
            <line x1="45" y1="45" x2="51" y2="51"/>
            <line x1="13" y1="51" x2="19" y2="45"/>
            <line x1="45" y1="19" x2="51" y2="13"/>
          </g>
        </svg>
        """
    if weather_code in {1, 2}:
        return """
        <svg viewBox="0 0 64 64" role="img" aria-label="Partly cloudy">
          <circle cx="24" cy="24" r="12" fill="#f6c445"/>
          <path d="M23 44h26c5 0 9-4 9-9s-4-9-9-9c-2 0-4 1-6 2-2-6-7-10-14-10-8 0-14 6-15 14-5 1-9 5-9 11 0 6 5 11 18 11z" fill="#ffffff" stroke="#9aa7b5" stroke-width="3" stroke-linejoin="round"/>
        </svg>
        """
    if weather_code == 3:
        return """
        <svg viewBox="0 0 64 64" role="img" aria-label="Cloudy">
          <path d="M18 46h31c6 0 11-5 11-11s-5-11-11-11c-2 0-5 1-7 2-3-7-9-12-17-12-10 0-18 8-19 18-5 2-9 7-9 13 0 7 6 13 21 13z" fill="#ffffff" stroke="#9aa7b5" stroke-width="3" stroke-linejoin="round"/>
        </svg>
        """
    if weather_code in {45, 48}:
        return """
        <svg viewBox="0 0 64 64" role="img" aria-label="Fog">
          <path d="M18 37h28c5 0 9-4 9-9s-4-9-9-9c-2 0-4 1-6 2-3-6-8-9-15-9-9 0-16 7-17 15-4 1-7 5-7 10 0 6 5 10 17 10z" fill="#ffffff" stroke="#9aa7b5" stroke-width="3" stroke-linejoin="round"/>
          <g stroke="#7b8794" stroke-width="4" stroke-linecap="round">
            <line x1="10" y1="45" x2="54" y2="45"/>
            <line x1="16" y1="53" x2="48" y2="53"/>
          </g>
        </svg>
        """
    if weather_code in {51, 53, 55, 61, 63, 65, 80, 81, 82}:
        return """
        <svg viewBox="0 0 64 64" role="img" aria-label="Rain">
          <path d="M18 37h30c6 0 10-4 10-10s-4-10-10-10c-2 0-4 1-6 2-3-6-8-10-16-10-9 0-16 7-17 16-5 1-8 5-8 11 0 6 5 11 17 11z" fill="#ffffff" stroke="#9aa7b5" stroke-width="3" stroke-linejoin="round"/>
          <g stroke="#2784d9" stroke-width="4" stroke-linecap="round">
            <line x1="21" y1="45" x2="17" y2="55"/>
            <line x1="34" y1="45" x2="30" y2="57"/>
            <line x1="47" y1="45" x2="43" y2="55"/>
          </g>
        </svg>
        """
    if weather_code in {71, 73, 75, 77, 85, 86}:
        return """
        <svg viewBox="0 0 64 64" role="img" aria-label="Snow">
          <path d="M18 37h30c6 0 10-4 10-10s-4-10-10-10c-2 0-4 1-6 2-3-6-8-10-16-10-9 0-16 7-17 16-5 1-8 5-8 11 0 6 5 11 17 11z" fill="#ffffff" stroke="#9aa7b5" stroke-width="3" stroke-linejoin="round"/>
          <g fill="#5bb4e5">
            <circle cx="21" cy="50" r="3"/>
            <circle cx="34" cy="54" r="3"/>
            <circle cx="47" cy="50" r="3"/>
          </g>
        </svg>
        """
    if weather_code in {95, 96, 99}:
        return """
        <svg viewBox="0 0 64 64" role="img" aria-label="Storm">
          <path d="M18 37h30c6 0 10-4 10-10s-4-10-10-10c-2 0-4 1-6 2-3-6-8-10-16-10-9 0-16 7-17 16-5 1-8 5-8 11 0 6 5 11 17 11z" fill="#ffffff" stroke="#9aa7b5" stroke-width="3" stroke-linejoin="round"/>
          <polygon points="33,39 24,57 34,53 30,63 43,44 33,48" fill="#f6c445"/>
        </svg>
        """
    return """
    <svg viewBox="0 0 64 64" role="img" aria-label="Weather">
      <path d="M18 46h31c6 0 11-5 11-11s-5-11-11-11c-2 0-5 1-7 2-3-7-9-12-17-12-10 0-18 8-19 18-5 2-9 7-9 13 0 7 6 13 21 13z" fill="#ffffff" stroke="#9aa7b5" stroke-width="3" stroke-linejoin="round"/>
    </svg>
    """


def format_forecast_text_line(forecast):
    location = forecast.get("location", {})
    place_parts = [location.get("city"), location.get("region"), location.get("country")]
    place = forecast.get("label") or ", ".join(part for part in place_parts if part) or "Local"
    return (
        f"- {place}: {weather_code_label(forecast.get('weather_code'))}, "
        f"{format_temp_pair(forecast.get('temperature_c'))}; "
        f"sensacao {format_temp_pair(forecast.get('feels_c'))}; "
        f"vento {format_forecast_wind(forecast.get('wind_kmh'), forecast.get('wind_direction_deg'))}; "
        f"chuva {format_forecast_rain_mm(forecast.get('precipitation_mm'))}"
    )


def news_source_logo_html(source):
    normalized = (source or "").strip().lower()
    if normalized == "globo.com":
        return """
        <span class='news-logo' aria-label='Globo.com'>
          <svg viewBox='0 0 170 36' role='img' aria-label='Globo.com'>
            <text x='0' y='25' font-family='Arial, Helvetica, sans-serif' font-size='25' font-weight='850' fill='#0068d9'>globo.com</text>
          </svg>
        </span>
        """
    if normalized == "uol":
        return """
        <span class='news-logo' aria-label='UOL'>
          <svg viewBox='0 0 116 36' role='img' aria-label='UOL'>
            <circle cx='18' cy='18' r='15' fill='#f15a24'/>
            <circle cx='18' cy='18' r='9' fill='#ffd400'/>
            <circle cx='18' cy='18' r='4.2' fill='#fff'/>
            <text x='41' y='25' font-family='Arial, Helvetica, sans-serif' font-size='24' font-weight='850' fill='#202124'>UOL</text>
          </svg>
        </span>
        """
    if normalized == "bloomberg":
        return """
        <span class='news-logo' aria-label='Bloomberg'>
          <svg viewBox='0 0 170 36' role='img' aria-label='Bloomberg'>
            <text x='0' y='25' font-family='Arial, Helvetica, sans-serif' font-size='25' font-weight='850' fill='#111827'>Bloomberg</text>
          </svg>
        </span>
        """
    if normalized == "cnbc":
        return """
        <span class='news-logo' aria-label='CNBC'>
          <svg viewBox='0 0 126 36' role='img' aria-label='CNBC'>
            <circle cx='13' cy='11' r='5.2' fill='#6f2dbd'/>
            <circle cx='22' cy='8' r='5.2' fill='#1f77d4'/>
            <circle cx='31' cy='11' r='5.2' fill='#00a651'/>
            <circle cx='15' cy='22' r='5.2' fill='#f6c000'/>
            <circle cx='29' cy='22' r='5.2' fill='#f58220'/>
            <circle cx='22' cy='17' r='5.2' fill='#e31b23'/>
            <text x='47' y='25' font-family='Arial, Helvetica, sans-serif' font-size='24' font-weight='850' fill='#202124'>CNBC</text>
          </svg>
        </span>
        """
    return (
        "<span class='news-logo'>"
        f"<strong>{html.escape(source or 'Fonte')}</strong>"
        "</span>"
    )


def render_news_item_html(item):
    title = item.get("title", "-")
    link = item.get("link", "")
    title_html = html.escape(title)
    if link:
        title_html = f"<a class='news-link' href='{html.escape(link, quote=True)}'>{title_html}</a>"
    else:
        title_html = f"<span class='news-link'>{title_html}</span>"
    published = html.escape(item.get("published") or "-")
    return f"<div class='news-item'>{title_html}<div class='news-time'>{published}</div></div>"


def render_news_table_html(news_groups):
    boxes = []
    for group in news_groups:
        source = group.get("source", "-")
        items = (group.get("items") or [])[:5]
        if items:
            body = "".join(render_news_item_html(item) for item in items)
        else:
            error = html.escape(group.get("error", "feed indisponivel"))
            body = f"<div class='news-error'>Indisponivel: {error}</div>"
        boxes.append(
            "<div class='news-box'>"
            f"<div class='news-box-head'>{news_source_logo_html(source)}"
            f"<span class='news-count'>{len(items)} noticias</span></div>"
            f"<div class='news-items'>{body}</div>"
            "</div>"
        )
    if not boxes:
        return "<div class='empty'>Noticias indisponiveis.</div>"
    return f"<div class='news-grid'>{''.join(boxes)}</div>"


def render_world_cup_panel_html(snapshot):
    if not snapshot.get("available"):
        error = snapshot.get("error", "jogos indisponiveis")
        return f"<div class='empty'>Brasileirao indisponivel: {html.escape(error)}.</div>"

    if snapshot.get("standings") or snapshot.get("current_matches") or snapshot.get("next_matches"):
        return render_brasileirao_panel_html(snapshot)

    result_rows = []
    upcoming_rows = []
    for item in snapshot.get("rows") or []:
        if is_world_cup_result_row(item):
            result_rows.append(
                "<tr>"
                f"<td>{render_world_cup_result_match_html(item)}</td>"
                "</tr>"
            )
            continue

        time_text = normalize_ws(item.get("time") or item.get("detail") or "-")
        upcoming_rows.append(
            "<tr>"
            f"<td>{render_world_cup_match_html(item)}</td>"
            f"<td><span class='world-cup-detail time'>{html.escape(time_text)}</span></td>"
            f"<td>{render_world_cup_location_html(item)}</td>"
            "</tr>"
        )

    results_html = render_world_cup_block_html(
        "Results",
        "world-cup-results-table",
        ("Result",),
        result_rows,
        "Sem resultados recentes encontrados.",
    )
    upcoming_html = render_world_cup_block_html(
        "Upcoming Matches",
        "world-cup-fixtures-table",
        ("Match", "Time", "Location"),
        upcoming_rows,
        "Sem proximos jogos encontrados.",
    )
    scorers = []
    for item in (snapshot.get("top_scorers") or [])[:5]:
        matches = item.get("matches")
        team_html = render_world_cup_team_html(item.get("team", "-"), item.get("team_flag"))
        scorers.append(
            "<tr>"
            f"<td><span class='world-cup-scorer-rank'>{html.escape(str(item.get('rank', '-')))}</span></td>"
            f"<td><strong>{html.escape(item.get('player', '-'))}</strong></td>"
            f"<td>{team_html}</td>"
            f"<td class='world-cup-goals'>{html.escape(str(item.get('goals', '-')))}</td>"
            f"<td>{html.escape(str(matches) if matches is not None else '-')}</td>"
            "</tr>"
        )
    scorers_html = ""
    if scorers:
        scorers_html = (
            "<div class='world-cup-scorers'>"
            "<div class='world-cup-scorers-title'>Top Scorers</div>"
            "<table class='world-cup-scorers-table'>"
            "<thead><tr><th>#</th><th>Player</th><th>Team</th><th>Goals</th><th>Matches</th></tr></thead>"
            f"<tbody>{''.join(scorers)}</tbody>"
            "</table>"
            "</div>"
        )
    source = snapshot.get("source") or "fontes disponiveis"
    scorer_source = snapshot.get("scorer_source")
    source_text = f"Source: {source}"
    if scorer_source and scorer_source != source:
        source_text = f"{source_text} | Top scorers: {scorer_source}"
    return (
        "<div class='world-cup-card'>"
        f"{results_html}"
        f"{upcoming_html}"
        f"{scorers_html}"
        f"<div class='world-cup-source'>{html.escape(source_text)}</div>"
        "</div>"
    )


def render_brasileirao_panel_html(snapshot):
    standings_html = render_brasileirao_standings_html(snapshot.get("standings") or [])
    current_html = render_brasileirao_matches_block_html(
        "Rodada atual",
        snapshot.get("current_matches") or [],
        "Sem jogos encontrados para a rodada atual.",
    )
    next_html = render_brasileirao_matches_block_html(
        "Proxima rodada",
        snapshot.get("next_matches") or [],
        "Sem jogos encontrados para a proxima rodada.",
    )
    scorers_html = render_brasileirao_scorers_html(snapshot.get("top_scorers") or [])
    source = snapshot.get("source") or "fontes disponiveis"
    return (
        "<div class='world-cup-card brasileirao-card'>"
        f"{standings_html}"
        "<div class='brasileirao-match-grid'>"
        f"{current_html}"
        f"{next_html}"
        "</div>"
        f"{scorers_html}"
        f"<div class='world-cup-source'>Source: {html.escape(source)}</div>"
        "</div>"
    )


def render_brasileirao_standings_html(rows):
    if not rows:
        body = "<tr><td colspan='8' class='muted'>Classificacao indisponivel.</td></tr>"
    else:
        body = "".join(
            "<tr>"
            f"<td class='brasileirao-rank'>{html.escape(str(item.get('rank', '-')))}</td>"
            f"<td>{render_world_cup_team_html(item.get('team', '-'), item.get('logo'))}</td>"
            f"<td>{html.escape(item.get('points', '-'))}</td>"
            f"<td>{html.escape(item.get('played', '-'))}</td>"
            f"<td>{html.escape(item.get('wins', '-'))}</td>"
            f"<td>{html.escape(item.get('ties', '-'))}</td>"
            f"<td>{html.escape(item.get('losses', '-'))}</td>"
            f"<td>{html.escape(item.get('goal_diff', '-'))}</td>"
            "</tr>"
            for item in rows[:20]
        )
    return (
        "<div class='world-cup-block brasileirao-standings-block'>"
        "<div class='world-cup-block-title'>Classificacao</div>"
        "<table class='world-cup-table brasileirao-standings-table'>"
        "<thead><tr><th>#</th><th>Clube</th><th>PTS</th><th>J</th><th>V</th><th>E</th><th>D</th><th>SG</th></tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
    )


def render_brasileirao_matches_block_html(title, rows, empty_text):
    if not rows:
        body = f"<tr><td colspan='3' class='muted'>{html.escape(empty_text)}</td></tr>"
    else:
        body = "".join(
            "<tr>"
            f"<td>{render_brasileirao_match_label_html(item)}</td>"
            f"<td><span class='world-cup-detail time'>{html.escape(item.get('detail') or item.get('time') or '-')}</span></td>"
            f"<td>{render_world_cup_location_html(item)}</td>"
            "</tr>"
            for item in rows[:10]
        )
    return (
        "<div class='world-cup-block brasileirao-matches-block'>"
        f"<div class='world-cup-block-title'>{html.escape(title)}</div>"
        "<table class='world-cup-table brasileirao-matches-table'>"
        "<thead><tr><th>Jogo</th><th>Hora/placar</th><th>Local</th></tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
    )


def render_brasileirao_match_label_html(item):
    home = normalize_ws(item.get("home_team") or "")
    away = normalize_ws(item.get("away_team") or "")
    if not home or not away:
        return f"<span class='brasileirao-match-label'>{html.escape(item.get('match', '-'))}</span>"
    return (
        "<span class='brasileirao-match-label'>"
        f"<strong>{html.escape(home)}</strong>"
        "<span> vs </span>"
        f"<strong>{html.escape(away)}</strong>"
        "</span>"
    )


def render_brasileirao_scorers_html(rows):
    scorers = []
    for item in rows[:5]:
        matches = item.get("matches")
        team_html = render_world_cup_team_html(item.get("team", "-"), item.get("team_flag"))
        scorers.append(
            "<tr>"
            f"<td><span class='world-cup-scorer-rank'>{html.escape(str(item.get('rank', '-')))}</span></td>"
            f"<td><strong>{html.escape(item.get('player', '-'))}</strong></td>"
            f"<td>{team_html}</td>"
            f"<td class='world-cup-goals'>{html.escape(str(item.get('goals', '-')))}</td>"
            f"<td>{html.escape(str(matches) if matches is not None else '-')}</td>"
            "</tr>"
        )
    if not scorers:
        return ""
    return (
        "<div class='world-cup-scorers brasileirao-scorers'>"
        "<div class='world-cup-scorers-title'>Artilheiros</div>"
        "<table class='world-cup-scorers-table'>"
        "<thead><tr><th>#</th><th>Jogador</th><th>Clube</th><th>Gols</th><th>Jogos</th></tr></thead>"
        f"<tbody>{''.join(scorers)}</tbody>"
        "</table>"
        "</div>"
    )


def render_world_cup_block_html(title, table_class, headers, rows, empty_text):
    if not rows:
        body = f"<tr><td colspan='{len(headers)}' class='muted'>{html.escape(empty_text)}</td></tr>"
    else:
        body = "".join(rows)
    return (
        "<div class='world-cup-block'>"
        f"<div class='world-cup-block-title'>{html.escape(title)}</div>"
        f"<table class='world-cup-table {html.escape(table_class)}'>"
        "<thead><tr>"
        + "".join(f"<th>{html.escape(header)}</th>" for header in headers)
        + "</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
    )


def is_world_cup_result_row(item):
    status = normalize_ws(item.get("status", "")).lower()
    detail = normalize_ws(item.get("detail", ""))
    return (
        item.get("period") == "Yesterday"
        or status.startswith("result")
        or status == "live"
        or bool(re.search(r"\d+\s*-\s*\d+", detail))
    )


def render_world_cup_result_match_html(item):
    home = normalize_ws(item.get("home_team") or "")
    away = normalize_ws(item.get("away_team") or "")
    if not home or not away:
        return f"<div class='world-cup-result-match'>{html.escape(item.get('match', '-'))}</div>"
    home_score, away_score = parse_world_cup_score_pair(item.get("detail"))
    if home_score is None or away_score is None:
        return render_world_cup_match_html(item)
    return (
        "<div class='world-cup-result-match'>"
        f"<span class='world-cup-result-side home'>{render_world_cup_team_html(home, item.get('home_flag'))}</span>"
        f"<span class='world-cup-result-score'>{html.escape(home_score)}</span>"
        "<span class='world-cup-vs'>vs</span>"
        f"<span class='world-cup-result-score'>{html.escape(away_score)}</span>"
        f"<span class='world-cup-result-side away'>{render_world_cup_team_html(away, item.get('away_flag'))}</span>"
        "</div>"
    )


def parse_world_cup_score_pair(value):
    match = re.search(r"(\d+)\s*-\s*(\d+)", normalize_ws(value or ""))
    if not match:
        return None, None
    return match.group(1), match.group(2)


def render_world_cup_match_html(item):
    home = normalize_ws(item.get("home_team") or "")
    away = normalize_ws(item.get("away_team") or "")
    if not home or not away:
        return f"<div class='world-cup-match'>{html.escape(item.get('match', '-'))}</div>"

    return (
        "<div class='world-cup-match'>"
        f"<span class='world-cup-match-side home'>{render_world_cup_team_html(home, item.get('home_flag'))}</span>"
        "<span class='world-cup-vs'>vs</span>"
        f"<span class='world-cup-match-side away'>{render_world_cup_team_html(away, item.get('away_flag'))}</span>"
        "</div>"
    )


def render_world_cup_team_html(name, flag_url):
    flag = normalize_ws(flag_url or WORLD_CUP_FLAG_URLS.get(name, ""))
    flag_html = ""
    if flag:
        flag_html = (
            f"<img class='world-cup-flag' src='{html.escape(flag, quote=True)}' "
            f"alt='{html.escape(name, quote=True)} flag'>"
        )
    return f"<span class='world-cup-team'>{flag_html}<span>{html.escape(name)}</span></span>"


def render_world_cup_location_html(item):
    stadium = normalize_ws(item.get("stadium") or "")
    region = normalize_ws(item.get("region") or "")
    if stadium and region:
        return f"<span class='world-cup-location'>{html.escape(stadium)}<br><span>{html.escape(region)}</span></span>"
    if stadium:
        return f"<span class='world-cup-location'>{html.escape(stadium)}</span>"
    return f"<span class='world-cup-location'>{html.escape(region or '-')}</span>"


def render_action_brief_panel_html(decisions, followups):
    def render_box(title, headers, rows, keys, empty_text):
        if rows:
            body = "".join(
                "<tr>"
                + "".join(f"<td>{html.escape(str(row.get(key, '') or '-'))}</td>" for key in keys)
                + "</tr>"
                for row in rows
            )
            table = (
                "<table class='action-table'>"
                "<thead><tr>"
                + "".join(f"<th>{html.escape(header)}</th>" for header in headers)
                + "</tr></thead>"
                f"<tbody>{body}</tbody>"
                "</table>"
            )
        else:
            table = f"<div class='empty'>{html.escape(empty_text)}</div>"
        return (
            "<div class='action-brief-box'>"
            f"<div class='action-brief-title'>{html.escape(title)}</div>"
            f"{table}"
            "</div>"
        )

    boxes = [
        render_box(
            "Decision Queue",
            ("Decisao", "Contexto", "Acao sugerida"),
            decisions,
            ("decision", "context", "action"),
            "Nenhuma decisao clara identificada nos emails recentes.",
        ),
        render_box(
            "Follow-ups Pendentes",
            ("Assunto", "Status", "Proximo passo"),
            followups,
            ("subject", "status", "next"),
            "Nenhum follow-up pendente identificado nos emails recentes.",
        ),
    ]
    return f"<div class='action-briefs'>{''.join(boxes)}</div>"


def render_automation_health_html(items):
    if not items:
        return ""
    cells = "".join(
        "<div class='health-item'>"
        f"<div class='health-label'>{html.escape(item.get('label', '-'))}</div>"
        f"<div class='health-value'>{html.escape(item.get('value', '-'))}</div>"
        "</div>"
        for item in items
    )
    return (
        "<div class='automation-health'>"
        "<div class='automation-health-title'>Automation Health</div>"
        f"<div class='automation-health-grid'>{cells}</div>"
        "</div>"
    )


def render_hourly_forecast_chart_html(points):
    points = [point for point in points if point.get("temperature_c") is not None or point.get("rain_pct") is not None]
    if not points:
        return ""

    width = 1000
    height = 172
    left = 4
    right = 4
    top = 25
    bottom = 30
    base_y = height - bottom
    chart_w = width - left - right
    chart_h = base_y - top
    temps = [point.get("temperature_c") for point in points if point.get("temperature_c") is not None]
    min_temp, max_temp = hourly_temperature_chart_domain(temps)

    def x_pos(idx):
        if len(points) == 1:
            return left + chart_w / 2
        band_w = chart_w / max(1, len(points))
        return left + (band_w * idx) + (band_w / 2)

    def temp_y(value):
        if value is None:
            return None
        return top + ((max_temp - value) / (max_temp - min_temp)) * chart_h

    grid = []
    for frac in (0, 0.5, 1):
        y = top + chart_h * frac
        grid.append(f"<line class='forecast-gridline' x1='{left}' y1='{y:.1f}' x2='{width - right}' y2='{y:.1f}'/>")
    grid.append(f"<line class='forecast-axis' x1='{left}' y1='{base_y}' x2='{width - right}' y2='{base_y}'/>")

    bars = []
    labels = []
    line_points = []
    for idx, point in enumerate(points):
        x = x_pos(idx)
        rain_pct = point.get("rain_pct")
        rain_value = max(0, min(100, float(rain_pct))) if rain_pct is not None else 0
        bar_h = chart_h * rain_value / 100
        band_w = chart_w / max(1, len(points))
        bar_w = max(24, band_w * 0.9)
        bars.append(
            f"<rect class='forecast-rain-bar' x='{x - bar_w / 2:.1f}' y='{base_y - bar_h:.1f}' "
            f"width='{bar_w:.1f}' height='{bar_h:.1f}' rx='2'/>"
        )
        temp = point.get("temperature_c")
        y = temp_y(temp)
        if y is not None:
            line_points.append((x, y))
            labels.append(f"<circle class='forecast-temp-dot' cx='{x:.1f}' cy='{y:.1f}' r='3.1'/>")
            labels.append(
                f"<text class='forecast-temp-label' x='{x:.1f}' y='{max(12, y - 8):.1f}' "
                "text-anchor='middle'>"
                f"{html.escape(format_temp_c_chart(temp))}</text>"
            )
        rain_label_y = base_y - bar_h - 7 if bar_h >= 12 else base_y - 8
        labels.append(
            f"<text class='forecast-rain-label' x='{x:.1f}' y='{rain_label_y:.1f}' "
            "text-anchor='middle'>"
            f"{rain_value:.0f}%</text>"
        )
        stamp = point.get("time")
        hour_label = stamp.strftime("%Hh") if hasattr(stamp, "strftime") else "-"
        labels.append(
            f"<text class='forecast-hour-label' x='{x:.1f}' y='{height - 8}' text-anchor='middle'>"
            f"{html.escape(hour_label)}</text>"
        )

    temp_path = smooth_svg_path(line_points)
    temp_line = f"<path class='forecast-temp-line' d='{temp_path}'/>" if temp_path else ""
    return (
        "<div class='forecast-hourly'>"
        "<div class='forecast-hourly-head'>"
        "<div class='forecast-hourly-title'>Hora a hora</div>"
        "<div class='forecast-legend'><span class='legend-temp'>Temp.</span><span class='legend-rain'>Chuva</span></div>"
        "</div>"
        f"<svg class='forecast-chart' width='100%' height='100%' viewBox='0 0 {width} {height}' role='img' aria-label='Temperatura e chance de chuva hora a hora'>"
        f"{''.join(grid)}{''.join(bars)}{temp_line}{''.join(labels)}"
        "</svg>"
        "</div>"
    )


def hourly_temperature_chart_domain(temps, min_span=8.0):
    if not temps:
        return 0, 1
    min_temp = min(temps)
    max_temp = max(temps)
    midpoint = (min_temp + max_temp) / 2
    span = max(max_temp - min_temp, min_span)
    span *= 1.08
    return midpoint - span / 2, midpoint + span / 2


def smooth_svg_path(points):
    if not points:
        return ""
    if len(points) == 1:
        x, y = points[0]
        return f"M {x:.1f} {y:.1f}"
    path = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for idx in range(len(points) - 1):
        p0 = points[idx - 1] if idx > 0 else points[idx]
        p1 = points[idx]
        p2 = points[idx + 1]
        p3 = points[idx + 2] if idx + 2 < len(points) else p2
        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = p1[1] + (p2[1] - p0[1]) / 6
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = p2[1] - (p3[1] - p1[1]) / 6
        path.append(
            f"C {c1x:.1f} {c1y:.1f}, {c2x:.1f} {c2y:.1f}, "
            f"{p2[0]:.1f} {p2[1]:.1f}"
        )
    return " ".join(path)


def forecast_day_label(date_value, idx):
    if idx == 0:
        return "Hoje"
    if idx == 1:
        return "Amanha"
    if not date_value:
        return f"D+{idx}"
    try:
        parsed = dt.date.fromisoformat(date_value)
        return parsed.strftime("%d/%m")
    except ValueError:
        return str(date_value)


def render_whatsapp_card_html(item):
    return (
        "<div class='card'>"
        f"<div class='card-head'><div class='card-title'>{html.escape(item['contact'])}</div><span class='badge'>{html.escape(item['priority'])}</span></div>"
        f"<div class='muted'>{html.escape(str(item['time']))} | {html.escape(str(item['unread_count']))} nao lida(s)</div>"
        f"<p>{html.escape(item['summary'])}</p>"
        f"<div><span class='label'>Resposta</span><br>{html.escape(item['reply'])}</div>"
        "</div>"
    )


def render_email_card_html(msg):
    received = msg["received"].strftime("%d/%m %H:%M") if msg["received"] else "-"
    classification = msg["classification"]
    cls = "high" if classification == "Alta atencao" else "reply" if classification == "Responder / revisar" else ""
    return (
        f"<div class='card email-card {cls}'>"
        f"<div class='card-head'><div><span class='badge {cls}'>{html.escape(classification)}</span></div><span class='muted'>{html.escape(received)}</span></div>"
        f"<div class='card-title'>{html.escape(msg['subject'])}</div>"
        f"<div class='muted'>{html.escape(msg['sender'])}</div>"
        f"<p>{html.escape(msg['summary'])}</p>"
        f"<div><span class='label'>Resposta sugerida</span><br>{html.escape(msg['reply'])}</div>"
        "</div>"
    )


def render_quarantine_row_html(msg):
    received = msg["received"].strftime("%d/%m %H:%M") if msg["received"] else "-"
    return (
        "<tr>"
        f"<td>{html.escape(msg['subject'])}</td>"
        f"<td>{html.escape(msg['sender'])}</td>"
        f"<td class='muted'>{html.escape(received)}</td>"
        "</tr>"
    )


def render_text(day, events, emails, markets, whatsapp_items, billfish, forecast=None, news=None, candidate_data=None, report_title="Morning Summary", automation_health=None, world_cup=None, brokerage_notes=None, pluggy=None):
    important = [e for e in emails if e["classification"] != "Quarentena sugerida"][:15]
    priorities = build_priorities(events, important)
    lines = [
        f"{report_title} - {day.strftime('%d/%m/%Y')}",
        f"Gerado em {dt.datetime.now(TIMEZONE).strftime('%d/%m/%Y %H:%M')}",
        "",
        "Markets",
    ]
    market_groups = [
        ("Index", {"ES=F", "NQ=F", "^N225", "^GDAXI", "000001.SS"}),
        ("Currencies", {"BRL=X", "EURBRL=X", "GBPBRL=X"}),
        ("CRIPTO", {"BTC-USD", "ETH-USD", "SOL-USD", "BONK-USD", "DOGE-USD"}),
        ("Portfolio Stocks", {"AMZN", "AVGO", "VOO", "TTWO", "SPCX", "KWEB", "MHVYF", "PRNR3.SA", "UNIP6.SA"}),
    ]
    by_symbol = {market["symbol"]: market for market in markets}
    for title, symbols in market_groups:
        lines.append(title)
        for label, symbol in MARKET_SYMBOLS:
            if symbol in symbols and symbol in by_symbol:
                market = by_symbol[symbol]
                lines.append(f"- {market['label']}: {format_market_line(market)}")

    lines.extend(["", "OPEN FINANCE"])
    if pluggy and pluggy.get("available"):
        lines.append(f"- Saldo corrente: {format_pluggy_money(pluggy.get('total_brl'), 'BRL')}")
        lines.append(f"- Faturas abertas: {format_pluggy_money(pluggy.get('total_card_balance_brl'), 'BRL')}")
        lines.append(f"- Investimentos: {format_pluggy_money(pluggy.get('total_investments_brl'), 'BRL')}")
        lines.append(f"- Despesas passadas 30d: {format_pluggy_money(pluggy.get('past_expenses', 0), 'BRL')}")
        lines.append(f"- Despesas futuras: {format_pluggy_money(pluggy.get('future_expenses', 0), 'BRL')}")
        for account in (pluggy.get("bank_accounts") or [])[:8]:
            lines.append(
                f"- {account.get('institution', '-')}: {account.get('name', '-')} "
                f"{account.get('number') or ''} | {format_pluggy_money(account.get('balance'), account.get('currency'))}"
            )
    else:
        lines.append(f"- Indisponivel/configurar: {(pluggy or {}).get('error', 'Pluggy nao configurado')}")

    lines.extend(["", "Billfish FIA"])
    lines.append(f"- {format_billfish_line(billfish)}")

    lines.extend(["", "Brokerage Notes"])
    lines.extend(format_brokerage_notes_lines(brokerage_notes or {}))

    lines.extend(["", "Candidate Stocks"])
    for group, items in CHEAP_STOCKS.items():
        lines.append(group)
        for item in items:
            ticker = item["ticker"]
            enriched = (candidate_data or {}).get(ticker, {})
            daily_change = enriched.get("daily_change", "N/D")
            daily_change_part = f" {daily_change}" if daily_change != "N/D" else ""
            lines.append(
                f"- {ticker}: Price: {strip_price_currency(enriched.get('price', 'N/D'))} "
                f"{daily_change_part} ({enriched.get('price_to_buy_in', 'N/D')} vs buy-in) | "
                f"{format_candidate_multiples_text(enriched.get('multiples') or item['multiples'])} | "
                f"Consensus: {enriched.get('consensus', CANDIDATE_TARGETS.get(ticker, 'N/D'))} | "
                f"Our TP: {enriched.get('model_target', enriched.get('target', 'N/D'))} "
                f"(Upside {enriched.get('upside', 'N/D')}) | "
                f"Buy-in: {enriched.get('buy_in', format_candidate_buy_in(ticker, None))} | "
                f"{item['thesis']} Risco: {item['risk']}"
            )

    lines.extend([
        "",
        "Agenda",
    ])
    if events:
        for event in events:
            if event["all_day"]:
                when = "Dia inteiro"
            elif event["start"] and event["end"]:
                when = f"{event['start'].strftime('%H:%M')} - {event['end'].strftime('%H:%M')}"
            else:
                when = "Horario nao disponivel"
            suffix = f" | {event['location']}" if event["location"] else ""
            lines.append(f"- {when} - {event['subject']}{suffix}")
    else:
        lines.append("- Sem compromissos encontrados na agenda.")

    lines.extend(["", "Forecast"])
    if forecast and forecast.get("available"):
        chart_locations = forecast.get("chart_locations") or ([forecast] if forecast.get("location") else [])
        for city_forecast in chart_locations:
            lines.append(format_forecast_text_line(city_forecast))
            hourly = city_forecast.get("hourly") or []
            if hourly:
                samples = []
                for point in hourly[:8]:
                    stamp = point.get("time")
                    hour = stamp.strftime("%Hh") if hasattr(stamp, "strftime") else "-"
                    temp = format_temp_c(point.get("temperature_c"))
                    rain_pct = point.get("rain_pct")
                    rain_text = f"{rain_pct:.0f}%" if rain_pct is not None else "-"
                    samples.append(f"{hour}: {temp}, chuva {rain_text}")
                lines.append(f"  Hora a hora: {'; '.join(samples)}")
        summary_locations = forecast.get("summary_locations") or []
        if summary_locations:
            lines.append("- Mini tabela:")
            for item in summary_locations:
                lines.append(
                    f"  {item.get('label', '-')}: {weather_code_label(item.get('weather_code'))}, "
                    f"{format_temp_pair(item.get('temperature_c'))}, "
                    f"chuva {format_forecast_rain_mm(item.get('precipitation_mm'))}, "
                    f"vento {format_forecast_wind(item.get('wind_kmh'), item.get('wind_direction_deg'))}"
                )
    else:
        error = (forecast or {}).get("error", "previsao indisponivel")
        lines.append(f"- Forecast indisponivel: {error}")

    lines.extend(["", "News"])
    for group in news or []:
        source = group.get("source", "-")
        items = group.get("items") or []
        if not items:
            lines.append(f"- {source}: indisponivel ({group.get('error', 'feed indisponivel')})")
            continue
        for item in items[:3]:
            published = item.get("published") or "-"
            link = f" | {item.get('link')}" if item.get("link") else ""
            lines.append(f"- {source}: {item.get('title', '-')} ({published}){link}")

    lines.extend(["", "Decision Queue"])
    decisions = build_decision_queue(important)
    if decisions:
        for item in decisions:
            lines.append(f"- {item['decision']}: {item['context']} | Acao: {item['action']}")
    else:
        lines.append("- Nenhuma decisao clara identificada nos emails recentes.")

    lines.extend(["", "Follow-ups Pendentes"])
    followups = build_followups(important, day)
    if followups:
        for item in followups:
            lines.append(f"- {item['subject']}: {item['status']} | Proximo passo: {item['next']}")
    else:
        lines.append("- Nenhum follow-up pendente identificado nos emails recentes.")

    lines.extend(["", "BRASILEIRAO"])
    if world_cup and world_cup.get("available"):
        standings = world_cup.get("standings") or []
        if standings:
            lines.append("Classificacao")
            for item in standings[:20]:
                lines.append(
                    f"- {item.get('rank', '-')}. {item.get('team', '-')} "
                    f"{item.get('points', '-')} pts | J {item.get('played', '-')} | "
                    f"V {item.get('wins', '-')} E {item.get('ties', '-')} D {item.get('losses', '-')} | SG {item.get('goal_diff', '-')}"
                )
        current_matches = world_cup.get("current_matches") or []
        if current_matches:
            lines.append("Rodada atual")
        for item in current_matches:
            lines.append(
                f"- {item.get('match', '-')} ({item.get('detail', '-')}) | "
                f"{item.get('region', '-')} | {item.get('stadium', '-')}"
            )
        next_matches = world_cup.get("next_matches") or []
        if next_matches:
            lines.append("Proxima rodada")
        for item in next_matches:
            lines.append(
                f"- {item.get('match', '-')} ({item.get('time', '-')}) | "
                f"{item.get('region', '-')} | {item.get('stadium', '-')}"
            )
        scorers = world_cup.get("top_scorers") or []
        if scorers:
            lines.append("Artilheiros")
            for item in scorers[:5]:
                matches = item.get("matches")
                matches_text = f", {matches} jogo(s)" if matches is not None else ""
                lines.append(
                    f"- {item.get('rank', '-')}. {item.get('player', '-')} "
                    f"({item.get('team', '-')}): {item.get('goals', '-')} gol(s){matches_text}"
                )
    else:
        lines.append(f"- Indisponivel: {(world_cup or {}).get('error', 'dados indisponiveis')}")

    lines.extend(["", "Automation Health"])
    for item in automation_health or []:
        lines.append(f"- {item.get('label', '-')}: {item.get('value', '-')}")

    lines.extend(["", "DAILY PRIORITIES"])
    for i, priority in enumerate(priorities, 1):
        lines.append(f"{i}. {priority}")
    return "\n".join(lines) + "\n"


def render_event(event):
    if event["all_day"]:
        when = "Dia inteiro"
    elif event["start"] and event["end"]:
        when = f"{event['start'].strftime('%H:%M')} - {event['end'].strftime('%H:%M')}"
    else:
        when = "Horario nao disponivel"
    location = f" <span class='muted'>| {html.escape(event['location'])}</span>" if event["location"] else ""
    return f"<li><strong>{html.escape(when)}</strong> - {html.escape(event['subject'])}{location}</li>"


def render_email(msg):
    received = msg["received"].strftime("%d/%m %H:%M") if msg["received"] else ""
    return (
        "<li class='email'>"
        f"<span class='tag'>{html.escape(msg['classification'])}</span> "
        f"<strong>{html.escape(msg['subject'])}</strong><br>"
        f"<span class='muted'>{html.escape(msg['sender'])} | {html.escape(received)}</span><br>"
        f"{html.escape(msg['summary'])}<br>"
        f"<em>Resposta sugerida:</em> {html.escape(msg['reply'])}"
        "</li>"
    )


def render_email_short(msg):
    received = msg["received"].strftime("%d/%m %H:%M") if msg["received"] else ""
    return f"<li><strong>{html.escape(msg['subject'])}</strong> <span class='muted'>| {html.escape(msg['sender'])} | {html.escape(received)}</span></li>"


def render_market_html(market):
    return f"<li><strong>{html.escape(market['label'])}</strong>: {html.escape(format_market_line(market))}</li>"


def render_billfish_html(billfish):
    return f"<li>{html.escape(format_billfish_line(billfish))}</li>"


def format_billfish_line(billfish):
    if not billfish.get("available"):
        return f"indisponivel ({billfish.get('error', 'sem detalhe')})"
    latest = billfish["latest"]
    ret = latest.get("daily_return_pct")
    ret_calc = latest.get("quota_change_calc")
    ret_part = format_pct(ret) if ret is not None else "retorno indisponivel"
    if ret_calc is not None and abs((ret or ret_calc) - ret_calc) > 0.01:
        ret_part += f" / calc. cota {format_pct(ret_calc)}"
    base = (
        f"Status {latest['date']} | daily change {ret_part} | "
        f"net worth {format_brl(latest['pl'])} | net worth change {format_brl_signed(latest['pl_change'])} | "
        f"fonte {billfish.get('source', latest.get('source', ''))}"
    )
    performance = billfish.get("performance") or {}
    if performance:
        base += (
            f" | Month: Billfish {format_optional_pct(performance.get('billfish_month_pct'))}, "
            f"Ibov {format_optional_pct(performance.get('ibov_month_pct'))}, "
            f"S&P 500 {format_optional_pct(performance.get('sp500_month_pct'))}, "
            f"CDI {format_optional_pct(performance.get('cdi_month_pct'))}"
            f" | Year: Billfish {format_optional_pct(performance.get('billfish_year_pct'))}, "
            f"Ibov {format_optional_pct(performance.get('ibov_year_pct'))}, "
            f"S&P 500 {format_optional_pct(performance.get('sp500_year_pct'))}, "
            f"CDI {format_optional_pct(performance.get('cdi_year_pct'))}, "
            f"IPCA 12M {format_optional_pct(performance.get('ipca_12m_pct'))}"
        )
    return base


def format_brokerage_notes_lines(snapshot):
    if not snapshot.get("available"):
        return [f"- indisponivel ({snapshot.get('error', 'sem detalhe')})"]
    lines = [
        (
            f"- {snapshot.get('trade_date') or '-'} | "
            f"{', '.join(snapshot.get('note_types') or ['Nota'])} | "
            f"Total negociado {format_brl(snapshot.get('total_traded') or 0)} | "
            f"Liquido {format_brl_signed(snapshot.get('net_total') or 0)}"
        )
    ]
    for trade in (snapshot.get("trades") or []):
        quantity = f"{trade.get('quantity'):,}".replace(",", ".") if trade.get("quantity") is not None else "-"
        price = trade.get("price")
        price_text = format_brl(price) if isinstance(price, (int, float)) else str(price or "-")
        value = format_brl(trade["value"]) if trade.get("value") is not None else "-"
        net = format_brl_signed(trade["net"]) if trade.get("net") is not None else "-"
        lines.append(
            f"  - {trade.get('type', '-')}: {trade.get('side', '-')} {trade.get('asset', '-')} "
            f"qtd {quantity} | preco/taxa {price_text} | valor {value} | liquido {net}"
        )
    summary_items = []
    for item in snapshot.get("financial_summary") or []:
        value = item.get("value")
        if value is None:
            continue
        value_text = format_brl_signed(value) if item.get("signed") else format_brl(value)
        summary_items.append(f"{item.get('label', '-')}: {value_text}")
    if summary_items:
        lines.append("  - Financial Summary: " + " | ".join(summary_items))
    return lines


def render_whatsapp_html(item):
    return (
        "<li>"
        f"<span class='tag'>{html.escape(item['priority'])}</span> "
        f"<strong>{html.escape(item['contact'])}</strong> "
        f"<span class='muted'>| {html.escape(str(item['time']))} | {html.escape(str(item['unread_count']))} nao lida(s)</span><br>"
        f"{html.escape(item['summary'])}<br>"
        f"<em>Resposta sugerida:</em> {html.escape(item['reply'])}"
        "</li>"
    )


def format_market_line(market):
    if market.get("price") is None:
        return market.get("state") or "indisponivel"
    price = format_market_price(market["symbol"], market["price"])
    change = market.get("change")
    pct = market.get("change_pct")
    if change is None or pct is None:
        move = "variacao indisponivel"
    else:
        move = f"{format_market_change(market['symbol'], change)} ({format_signed_pct(pct)})"
    when = market["time"].strftime("%H:%M") if market.get("time") else "horario indisponivel"
    return f"{price} | {move} | {when}"


def format_market_price(symbol, value):
    if value is None:
        return "-"
    if symbol in {"BTC-USD", "ETH-USD"}:
        return f"US$ {value:,.0f}"
    if symbol == "BONK-USD":
        return f"US$ {value:.8f}"
    if symbol in {"SOL-USD", "DOGE-USD"}:
        return f"US$ {value:,.4f}"
    if symbol in {"BRL=X", "EURBRL=X", "GBPBRL=X"}:
        return f"R$ {value:,.4f}"
    if symbol.endswith(".SA"):
        return f"R$ {value:,.2f}"
    if symbol in {"AMZN", "AVGO", "VOO", "TTWO", "SPCX", "KWEB", "MHVYF"}:
        return f"US$ {value:,.2f}"
    return f"{value:,.2f}"


def format_market_change(symbol, value):
    sign = "+" if value >= 0 else "-"
    abs_value = abs(value)
    if symbol in {"BTC-USD", "ETH-USD"}:
        return f"{sign}US$ {abs_value:,.0f}"
    if symbol == "BONK-USD":
        return f"{sign}US$ {abs_value:.8f}"
    if symbol in {"SOL-USD", "DOGE-USD"}:
        return f"{sign}US$ {abs_value:,.4f}"
    if symbol in {"BRL=X", "EURBRL=X", "GBPBRL=X"}:
        return f"{sign}R$ {abs_value:,.4f}"
    if symbol.endswith(".SA"):
        return f"{sign}R$ {abs_value:,.2f}"
    if symbol in {"AMZN", "AVGO", "VOO", "TTWO", "SPCX", "KWEB", "MHVYF"}:
        return f"{sign}US$ {abs_value:,.2f}"
    return f"{sign}{abs_value:,.2f}"


def strip_price_currency(value):
    return re.sub(r"^(R\$|US\$)\s*", "", str(value or "")).strip()


def format_signed_pct(value):
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.2f}%"


def format_pct(value):
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def format_optional_pct(value):
    return format_pct(value) if value is not None else "N/D"


def format_brl(value):
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_brl_signed(value):
    if abs(value) < 0.005:
        return format_brl(0)
    sign = "+" if value >= 0 else "-"
    return sign + format_brl(abs(value))


def build_priorities(events, emails):
    priorities = []
    high = [e for e in emails if e["classification"] == "Alta atencao"]
    reply = [e for e in emails if e["classification"] == "Responder / revisar"]
    if events:
        priorities.append("Checar compromissos fixos da agenda e separar deslocamentos/preparacao.")
    if high:
        priorities.append(f"Revisar {len(high)} email(s) de alta atencao antes de qualquer execucao financeira/juridica.")
    if reply:
        priorities.append(f"Responder ou encaminhar {min(len(reply), 5)} email(s) que pedem retorno.")
    while len(priorities) < 3:
        priorities.append("Reservar um bloco de foco para a principal pendencia operacional do dia.")
    return priorities[:3]


def make_pdf(html_path, pdf_path):
    result = subprocess.run(
        ["cupsfilter", html_path.as_posix()],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 or not result.stdout.startswith(b"%PDF"):
        return False, result.stderr.decode("utf-8", errors="replace")[:500]
    pdf_path.write_bytes(result.stdout)
    return True, "ok"


def make_chromium_pdf(html_path, pdf_path):
    candidates = [
        os.getenv("CHROME_BIN"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    chrome_bin = next((path for path in candidates if path and Path(path).exists()), None)
    if not chrome_bin:
        return False, "Chromium/Chrome indisponivel"
    result = subprocess.run(
        [
            chrome_bin,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            f"--print-to-pdf={pdf_path.resolve().as_posix()}",
            html_path.resolve().as_uri(),
        ],
        text=True,
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0 or not pdf_path.exists():
        detail = (result.stderr or result.stdout or "sem detalhe").strip()
        return False, detail[:700]
    return True, "chromium"


def make_reportlab_pdf(day, events, emails, markets, whatsapp_items, billfish, text_content, pdf_path, report_title="Morning Summary"):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        return False, f"reportlab unavailable: {exc}"

    important = [e for e in emails if e["classification"] != "Quarentena sugerida"][:15]
    quarantine = [e for e in emails if e["classification"] == "Quarentena sugerida"][:10]
    high = [e for e in important if e["classification"] == "Alta atencao"]
    reply = [e for e in important if e["classification"] == "Responder / revisar"]
    priorities = build_priorities(events, important)
    generated = dt.datetime.now(TIMEZONE).strftime("%d/%m/%Y %H:%M")

    doc = SimpleDocTemplate(
        pdf_path.as_posix(),
        pagesize=A4,
        rightMargin=1.25 * cm,
        leftMargin=1.25 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.3 * cm,
        title=f"{report_title} - {day.strftime('%d/%m/%Y')}",
        author="Chief of Staff Digital",
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Kicker",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=colors.HexColor("#52616f"),
            uppercase=True,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TitleCustom",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=27,
            textColor=colors.white,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="MetaRight",
            parent=styles["Normal"],
            alignment=TA_RIGHT,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#d0d7de"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=colors.white,
            spaceBefore=14,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionDark",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=colors.white,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#475467"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyCustom",
            parent=styles["Normal"],
            fontSize=9.5,
            leading=12.5,
            textColor=colors.HexColor("#17202a"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="EmailTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=colors.HexColor("#17202a"),
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="MetricValue",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=24,
            textColor=colors.HexColor("#111827"),
        )
    )

    story = []

    def section(title):
        table = Table([[Paragraph(title.upper(), styles["SectionDark"])]], colWidths=[18.5 * cm], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1f2937")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return [Spacer(1, 12), table, Spacer(1, 7)]

    story.append(
        Table(
            [
                [
                    [
                        Paragraph("CHIEF OF STAFF DIGITAL", styles["Kicker"]),
                        Paragraph(xml_escape(report_title), styles["TitleCustom"]),
                        Paragraph(f"<font color='#d0d7de'>Eduardo Castro | {day.strftime('%d/%m/%Y')}</font>", styles["Small"]),
                    ],
                    Paragraph(f"Gerado em<br/>{generated}", styles["MetaRight"]),
                ]
            ],
            colWidths=[13.2 * cm, 5.3 * cm],
        )
    )
    story[-1].setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ]
        )
    )

    metrics = [
        ("Agenda", str(len(events)), "compromissos hoje"),
        ("WhatsApp", str(whatsapp_unread_messages), "mensagens nao lidas"),
        ("Alta atencao", str(len(high)), "emails sensiveis"),
        ("Responder", str(len(reply)), "pedem retorno"),
        ("Quarentena", str(len(quarantine)), "spam/newsletters"),
    ]
    metric_cells = []
    for label, value, note in metrics:
        inner = Table(
            [
                [Paragraph(f"<b>{label}</b>", styles["Small"])],
                [Paragraph(value, styles["MetricValue"])],
                [Paragraph(note, styles["Small"])],
            ],
            colWidths=[3.35 * cm],
            rowHeights=[0.42 * cm, 0.72 * cm, 0.42 * cm],
        )
        inner.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        metric_cells.append(inner)
    metrics_table = Table([metric_cells], colWidths=[3.7 * cm] * 5)
    metrics_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#d0d7de")),
                ("INNERGRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#d9dee7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(Spacer(1, 12))
    story.append(metrics_table)

    story.extend(section("Markets"))
    market_rows = [[
        Paragraph("<b>COMPANY</b>", styles["Small"]),
        Paragraph("<b>PRICE</b>", styles["Small"]),
        Paragraph("<b>CHANGE</b>", styles["Small"]),
        Paragraph("<b>TIME</b>", styles["Small"]),
    ]]
    for market in markets:
        price = strip_price_currency(format_market_price(market["symbol"], market["price"])) if market.get("price") is not None else "-"
        change = market.get("change")
        pct = market.get("change_pct")
        if change is None or pct is None:
            move = market.get("state") or "indisponivel"
            color = "#667085"
        else:
            move = format_signed_pct(pct)
            color = "#067647" if change >= 0 else "#b42318"
        when = market["time"].strftime("%H:%M") if market.get("time") else "-"
        market_rows.append(
            [
                Paragraph(f"<b>{xml_escape(market['label'])}</b>", styles["BodyCustom"]),
                Paragraph(xml_escape(price), styles["BodyCustom"]),
                Paragraph(f"<font color='{color}'><b>{xml_escape(move)}</b></font>", styles["BodyCustom"]),
                Paragraph(when, styles["Small"]),
            ]
        )
    market_table = Table(market_rows, colWidths=[4.3 * cm, 4.4 * cm, 7.0 * cm, 2.8 * cm], hAlign="LEFT", repeatRows=1)
    market_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fbfcfe")]),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d9dee7")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#edf0f4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(market_table)

    story.extend(section("Billfish FIA"))
    story.append(billfish_card(billfish, styles))

    story.extend(section("DAILY PRIORITIES"))
    priority_rows = [[Paragraph(f"<b>{idx}</b>", styles["BodyCustom"]), Paragraph(priority, styles["BodyCustom"])] for idx, priority in enumerate(priorities, 1)]
    story.append(make_clean_table(priority_rows, [0.85 * cm, 15.35 * cm], subtle=False))

    story.extend(section("Agenda"))
    if events:
        rows = [[Paragraph("<b>Horario</b>", styles["Small"]), Paragraph("<b>Compromisso</b>", styles["Small"]), Paragraph("<b>Local</b>", styles["Small"])]]
        for event in events:
            if event["all_day"]:
                when = "Dia inteiro"
            elif event["start"] and event["end"]:
                when = f"{event['start'].strftime('%H:%M')} - {event['end'].strftime('%H:%M')}"
            else:
                when = "N/D"
            rows.append(
                [
                    Paragraph(when, styles["BodyCustom"]),
                    Paragraph(xml_escape(event["subject"]), styles["BodyCustom"]),
                    Paragraph(xml_escape(event["location"] or "-"), styles["Small"]),
                ]
            )
        story.append(make_grid_table(rows, [2.7 * cm, 9.7 * cm, 3.8 * cm]))
    else:
        story.append(Paragraph("Sem compromissos encontrados na agenda.", styles["BodyCustom"]))

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d0d7de"))
        canvas.line(1.6 * cm, 1.05 * cm, A4[0] - 1.6 * cm, 1.05 * cm)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(1.6 * cm, 0.65 * cm, "Chief of Staff Digital - modo leitura, sem apagar ou responder automaticamente")
        canvas.drawRightString(A4[0] - 1.6 * cm, 0.65 * cm, f"Pagina {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return True, "reportlab"


def make_clean_table(rows, widths, subtle=True):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, colWidths=widths, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if subtle:
        commands.append(("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#edf0f4")))
    table.setStyle(TableStyle(commands))
    return table


def make_grid_table(rows, widths, font_size=9):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, colWidths=widths, hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#344054")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d9dee7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ]
        )
    )
    return table


def email_card(msg, styles):
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

    received = msg["received"].strftime("%d/%m %H:%M") if msg["received"] else "-"
    palette = {
        "Alta atencao": ("#fff3e8", "#b54708"),
        "Responder / revisar": ("#eef4ff", "#175cd3"),
        "Arquivar / informativo": ("#f4f6f8", "#475467"),
    }
    bg, fg = palette.get(msg["classification"], ("#f4f6f8", "#475467"))
    badge = f"<font color='{fg}'><b>{xml_escape(msg['classification'])}</b></font>"
    content = [
        [
            Paragraph(badge, styles["Small"]),
            Paragraph(f"{xml_escape(msg['sender'])} | {received}", styles["Small"]),
        ],
        [Paragraph(xml_escape(msg["subject"]), styles["EmailTitle"]), ""],
        [Paragraph(f"<b>Resumo:</b> {xml_escape(msg['summary'])}", styles["BodyCustom"]), ""],
        [Paragraph(f"<b>Resposta sugerida:</b> {xml_escape(msg['reply'])}", styles["Small"]), ""],
    ]
    table = Table(content, colWidths=[4.1 * cm, 12.1 * cm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 1), (-1, 1)),
                ("SPAN", (0, 2), (-1, 2)),
                ("SPAN", (0, 3), (-1, 3)),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#d9dee7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return KeepTogether([table, Spacer(1, 7)])


def whatsapp_card(item, styles):
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

    palette = {
        "Alta atencao": ("#fff3e8", "#b54708"),
        "Responder": ("#eef4ff", "#175cd3"),
        "Revisar": ("#f4f6f8", "#475467"),
    }
    bg, fg = palette.get(item["priority"], ("#f4f6f8", "#475467"))
    badge = f"<font color='{fg}'><b>{xml_escape(item['priority'])}</b></font>"
    meta = f"{xml_escape(item['time'])} | {item['unread_count']} nao lida(s)"
    content = [
        [Paragraph(badge, styles["Small"]), Paragraph(meta, styles["Small"])],
        [Paragraph(xml_escape(item["contact"]), styles["EmailTitle"]), ""],
        [Paragraph(f"<b>Resumo:</b> {xml_escape(item['summary'])}", styles["BodyCustom"]), ""],
        [Paragraph(f"<b>Resposta sugerida:</b> {xml_escape(item['reply'])}", styles["Small"]), ""],
    ]
    table = Table(content, colWidths=[4.1 * cm, 12.1 * cm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 1), (-1, 1)),
                ("SPAN", (0, 2), (-1, 2)),
                ("SPAN", (0, 3), (-1, 3)),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#d9dee7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return KeepTogether([table, Spacer(1, 7)])


def billfish_card(billfish, styles):
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

    if not billfish.get("available"):
        table = Table(
            [[Paragraph("<b>Billfish FIA</b>", styles["EmailTitle"]), Paragraph(xml_escape(billfish.get("error", "indisponivel")), styles["Small"])]],
            colWidths=[4.1 * cm, 12.1 * cm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f6f8")),
                    ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#d9dee7")),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return KeepTogether([table, Spacer(1, 7)])

    latest = billfish["latest"]
    ret = latest.get("daily_return_pct")
    ret_color = "#067647" if ret is not None and ret >= 0 else "#b42318"
    pl_change = latest.get("pl_change")
    pl_color = "#067647" if pl_change is not None and pl_change >= 0 else "#b42318"
    cells = [
        [
            Paragraph("<b>STATUS</b>", styles["Small"]),
            Paragraph("<b>DAILY CHANGE</b>", styles["Small"]),
            Paragraph("<b>NET WORTH</b>", styles["Small"]),
            Paragraph("<b>NET WORTH CHANGE</b>", styles["Small"]),
        ],
        [
            Paragraph(xml_escape(latest["date"]), styles["BodyCustom"]),
            Paragraph(f"<font color='{ret_color}'><b>{xml_escape(format_pct(ret)) if ret is not None else 'N/D'}</b></font>", styles["BodyCustom"]),
            Paragraph(f"<b>{xml_escape(format_brl(latest['pl']))}</b>", styles["BodyCustom"]),
            Paragraph(f"<font color='{pl_color}'><b>{xml_escape(format_brl_signed(pl_change))}</b></font>", styles["BodyCustom"]),
        ],
        [
            Paragraph(f"Fonte: {xml_escape(billfish.get('source', latest.get('source', '')))}", styles["Small"]),
            "",
            "",
            "",
        ],
    ]
    table = Table(cells, colWidths=[3.1 * cm, 3.8 * cm, 4.7 * cm, 4.6 * cm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfcfe")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
                ("SPAN", (0, 2), (-1, 2)),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d9dee7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    flowables = [table, Spacer(1, 7)]
    performance = billfish.get("performance") or {}
    if performance:
        perf_rows = [
            [
                Paragraph("<b>INDEX</b>", styles["Small"]),
                Paragraph("<b>MONTH</b>", styles["Small"]),
                Paragraph("<b>YEAR</b>", styles["Small"]),
            ],
            [
                Paragraph("Billfish FIA", styles["BodyCustom"]),
                Paragraph(colored_pct(performance.get("billfish_month_pct")), styles["BodyCustom"]),
                Paragraph(colored_pct(performance.get("billfish_year_pct")), styles["BodyCustom"]),
            ],
            [
                Paragraph("Ibovespa", styles["BodyCustom"]),
                Paragraph(colored_pct(performance.get("ibov_month_pct")), styles["BodyCustom"]),
                Paragraph(colored_pct(performance.get("ibov_year_pct")), styles["BodyCustom"]),
            ],
            [
                Paragraph("S&P 500", styles["BodyCustom"]),
                Paragraph(colored_pct(performance.get("sp500_month_pct")), styles["BodyCustom"]),
                Paragraph(colored_pct(performance.get("sp500_year_pct")), styles["BodyCustom"]),
            ],
            [
                Paragraph("CDI", styles["BodyCustom"]),
                Paragraph(colored_pct(performance.get("cdi_month_pct")), styles["BodyCustom"]),
                Paragraph(colored_pct(performance.get("cdi_year_pct")), styles["BodyCustom"]),
            ],
            [
                Paragraph("IPCA 12M", styles["BodyCustom"]),
                Paragraph("-", styles["BodyCustom"]),
                Paragraph(colored_pct(performance.get("ipca_12m_pct")), styles["BodyCustom"]),
            ],
        ]
        perf_table = Table(perf_rows, colWidths=[6.2 * cm, 5.0 * cm, 5.0 * cm], hAlign="LEFT")
        perf_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d9dee7")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        flowables.extend([perf_table, Spacer(1, 7)])
    return KeepTogether(flowables)


def colored_pct(value):
    if value is None:
        return "N/D"
    color = "#067647" if value >= 0 else "#b42318"
    return f"<font color='{color}'><b>{xml_escape(format_pct(value))}</b></font>"


def xml_escape(value):
    return html.escape(str(value or "")).replace("\n", "<br/>")


def make_simple_pdf(text_content, pdf_path):
    lines = []
    for raw in text_content.splitlines():
        wrapped = textwrap.wrap(raw, width=92, replace_whitespace=False) or [""]
        lines.extend(wrapped)

    pages = [lines[i : i + 48] for i in range(0, len(lines), 48)] or [[]]
    objects = []

    def add_object(content):
        objects.append(content)
        return len(objects)

    page_ids = []
    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page_lines in pages:
        stream_lines = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        for idx, line in enumerate(page_lines):
            if idx:
                stream_lines.append("T*")
            stream_lines.append(f"({pdf_escape(line)}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("cp1252", errors="replace")
        content_id = add_object(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        )
        page_id = add_object(
            f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode(
                "ascii"
            )
        )
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_id = add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii"))

    # Patch parent references now that /Pages id is known.
    for pid in page_ids:
        objects[pid - 1] = objects[pid - 1].replace(b"/Parent 0 0 R", f"/Parent {pages_id} 0 R".encode("ascii"))

    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))
    chunks = [b"%PDF-1.4\n"]
    offsets = [0]
    for idx, obj in enumerate(objects, 1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{idx} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in chunks)
    chunks.append(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    chunks.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        chunks.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    chunks.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "ascii"
        )
    )
    pdf_path.write_bytes(b"".join(chunks))
    return True, "ok"


def pdf_escape(value):
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def send_email(password, subject, body, attachments):
    sent, ews_msg = send_email_ews(password, subject, body, attachments)
    if sent:
        return sent, ews_msg

    msg = email.message.EmailMessage()
    msg["From"] = ACCOUNT
    msg["To"] = ACCOUNT
    msg["Subject"] = subject
    msg.set_content(body)
    for path in attachments:
        data = path.read_bytes()
        maintype, subtype = ("application", "pdf") if path.suffix == ".pdf" else ("text", "html")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)

    last_error = None
    for host, port, starttls in (
        (SERVER, 587, True),
        (SERVER, 465, False),
        (SERVER, 25, True),
    ):
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                    smtp.login(ACCOUNT, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    smtp.ehlo()
                    if starttls:
                        smtp.starttls(context=ssl.create_default_context())
                        smtp.ehlo()
                    smtp.login(ACCOUNT, password)
                    smtp.send_message(msg)
            return True, f"SMTP {host}:{port}"
        except (OSError, smtplib.SMTPException, socket.timeout) as exc:
            last_error = f"{host}:{port} - {type(exc).__name__}: {exc}"
    smtp_msg = last_error or "SMTP failed"
    return False, f"{ews_msg}; SMTP fallback: {smtp_msg}"


def send_email_ews(password, subject, body_text, attachments):
    attachment_xml = ""
    for path in attachments:
        content = base64.b64encode(path.read_bytes()).decode("ascii")
        attachment_xml += f"""
          <t:FileAttachment>
            <t:Name>{html.escape(path.name)}</t:Name>
            <t:Content>{content}</t:Content>
          </t:FileAttachment>"""
    body_xml = f"""
<m:CreateItem MessageDisposition="SendAndSaveCopy">
  <m:SavedItemFolderId>
    <t:DistinguishedFolderId Id="sentitems" />
  </m:SavedItemFolderId>
  <m:Items>
    <t:Message>
      <t:Subject>{html.escape(subject)}</t:Subject>
      <t:Importance>High</t:Importance>
      <t:Categories>
        <t:String>Red Category</t:String>
      </t:Categories>
      <t:Flag>
        <t:FlagStatus>Flagged</t:FlagStatus>
      </t:Flag>
      <t:Body BodyType="Text">{html.escape(body_text)}</t:Body>
      <t:ToRecipients>
        <t:Mailbox>
          <t:EmailAddress>{html.escape(ACCOUNT)}</t:EmailAddress>
        </t:Mailbox>
      </t:ToRecipients>
      <t:Attachments>{attachment_xml}
      </t:Attachments>
    </t:Message>
  </m:Items>
</m:CreateItem>"""
    try:
        data = ews_request(password, body_xml)
        root = ET.fromstring(data)
        response = root.find(".//m:CreateItemResponseMessage", NS)
        if response is not None and response.attrib.get("ResponseClass") == "Success":
            return True, "EWS SendAndSaveCopy"
        code = text(root, ".//m:ResponseCode", "unknown")
        message = text(root, ".//m:MessageText", "")
        return False, f"EWS send failed: {code} {message}"
    except Exception as exc:
        return False, f"EWS send failed: {type(exc).__name__}: {exc}"


def format_moved_by_folder(moved_by_folder):
    if not moved_by_folder:
        return "nenhum"
    return "; ".join(
        f"{folder}: {count}"
        for folder, count in sorted(moved_by_folder.items())
        if count
    ) or "nenhum"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--organize", action="store_true", help="Legacy flag kept for compatibility; emails stay in Inbox unless --move-emails is also provided.")
    parser.add_argument("--archive-informative", action="store_true", help="Suggest informative/no-action archive folders by subject.")
    parser.add_argument("--move-emails", action="store_true", help="Actually move classified emails out of Inbox. Use only for manual cleanup.")
    parser.add_argument("--limit", type=int, default=250, help="Number of inbox emails to scan.")
    parser.add_argument("--no-send", action="store_true", help="Generate files but do not send the summary email.")
    parser.add_argument("--audit-only", action="store_true", help="Only scan and write the audit CSV; do not move items or send email.")
    parser.add_argument("--whatsapp-json", help="Optional JSON file with WhatsApp unread summaries.")
    parser.add_argument("--skip-candidate-data", action="store_true", help="Skip Candidate Stocks network refresh for manual send/layout tests.")
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    password = keychain_password()
    run_at = dt.datetime.now(TIMEZONE)
    today = run_at.date()
    stamp = today.strftime("%Y-%m-%d")
    report_title = report_title_for_time(run_at)
    output_slug = report_slug(report_title)
    organize = args.move_emails and not args.audit_only
    moved_to_quarantine = 0
    moved_by_folder = {}
    folders_ready = []

    emails = find_recent_emails(password, limit=args.limit)
    for msg in emails:
        msg["classification"] = classify_email(msg)
        msg["summary"] = summarize_email(msg)
        msg["reply"] = suggested_reply(msg, msg["classification"])
        msg["target_folder"] = route_email_folder(msg, include_informative=args.archive_informative)

    if organize:
        folders = ensure_operational_folders(password)
        folders_ready = list(folders.keys())
        moved_by_folder = organize_classified_items(password, emails, folders, include_informative=args.archive_informative)
        moved_to_quarantine = moved_by_folder.get("Quarentena - Spam Provavel", 0)

    skip_candidate_data = args.skip_candidate_data or os.getenv("CANDIDATE_SKIP_DATA", "").lower() in {"1", "true", "yes"}
    events = find_calendar_today(password, today)
    markets = fetch_market_snapshot()
    forecast = fetch_weather_forecast()
    news = fetch_news_snapshot()
    world_cup = fetch_brasileirao_snapshot(today)
    pluggy = fetch_pluggy_snapshot()
    whatsapp_items = load_whatsapp_items(args.whatsapp_json)
    billfish = fetch_billfish_snapshot(password)
    brokerage_notes = fetch_brokerage_notes_snapshot(password)
    global CHEAP_STOCKS
    if skip_candidate_data:
        candidate_data = {}
    else:
        try:
            CHEAP_STOCKS = build_dynamic_candidate_stocks()
        except Exception as exc:
            print(f"Dynamic candidate screening failed, using fallback list: {type(exc).__name__}: {exc}", file=sys.stderr)
        candidate_data = build_candidate_stock_data()
    pdf_delivery_status = "teste local" if args.no_send or args.audit_only else "sim"
    automation_health = build_automation_health(emails, whatsapp_items, billfish, pluggy, pdf_delivery_status=pdf_delivery_status)
    html_doc = render_html(today, events, emails, markets, whatsapp_items, billfish, forecast, news, candidate_data, report_title, automation_health, world_cup, brokerage_notes, pluggy)
    text_doc = render_text(today, events, emails, markets, whatsapp_items, billfish, forecast, news, candidate_data, report_title, automation_health, world_cup, brokerage_notes, pluggy)
    html_path = OUT_DIR / f"{output_slug}-{stamp}.html"
    text_path = OUT_DIR / f"{output_slug}-{stamp}.txt"
    pdf_path = OUT_DIR / f"{output_slug}-{stamp}.pdf"
    audit_path = OUT_DIR / f"auditoria-email-{stamp}.csv"
    html_path.write_text(html_doc, encoding="utf-8")
    text_path.write_text(text_doc, encoding="utf-8")
    write_audit_csv(audit_path, emails)

    pdf_ok, pdf_msg = make_chromium_pdf(html_path, pdf_path)
    if not pdf_ok:
        pdf_ok, pdf_msg = make_reportlab_pdf(today, events, emails, markets, whatsapp_items, billfish, text_doc, pdf_path, report_title)
    if not pdf_ok:
        pdf_ok, pdf_msg = make_pdf(html_path, pdf_path)
    if not pdf_ok:
        pdf_ok, pdf_msg = make_simple_pdf(text_doc, pdf_path)
    attachments = [pdf_path] if pdf_ok else [html_path]
    subject = f"{report_title} - {today.strftime('%d/%m/%Y')}"
    body = textwrap.dedent(
        f"""\
        Eduardo,

        Segue o {report_title} de hoje.

        Agenda: {len(events)} compromisso(s)
        WhatsApp: {count_whatsapp_unread_messages(whatsapp_items)} mensagem(ns) nao lida(s)
        Billfish FIA: {'ok' if billfish.get('available') else 'indisponivel'}
        Brokerage Notes: {'ok' if brokerage_notes.get('available') else 'indisponivel'}
        Open Finance: {'ok' if pluggy.get('available') else pluggy.get('error', 'indisponivel')}
        Emails analisados: {len(emails)}
        Pastas operacionais: {'criadas/verificadas' if organize else 'nao alteradas'}
        Emails movidos para quarentena: {moved_to_quarantine}
        Emails organizados em pastas: {sum(moved_by_folder.values())}
        Movimentos por pasta: {format_moved_by_folder(moved_by_folder)}
        Anexo: {'PDF' if pdf_ok else 'HTML (PDF nao gerado: ' + pdf_msg + ')'}

        Abs.,
        Chief of Staff Digital
        """
    )
    if args.no_send or args.audit_only:
        sent, send_msg = True, "skipped by --no-send/--audit-only"
    else:
        sent, send_msg = send_email(password, subject, body, attachments)

    print(f"HTML: {html_path}")
    print(f"PDF: {pdf_path if pdf_ok else 'not generated - ' + pdf_msg}")
    print(f"Audit: {audit_path}")
    print(f"Folders ready: {', '.join(folders_ready) if folders_ready else 'not changed'}")
    print(f"Moved to quarantine: {moved_to_quarantine}")
    print(f"Moved by folder: {sum(moved_by_folder.values())} ({moved_by_folder})")
    print(f"Email sent: {'yes' if sent else 'no'} ({send_msg})")
    return 0 if sent else 3


if __name__ == "__main__":
    sys.exit(main())
