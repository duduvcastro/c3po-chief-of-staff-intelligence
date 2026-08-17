#!/usr/bin/env python3
import argparse
import asyncio
import datetime as dt
import json
import os
import re
from pathlib import Path

from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo(os.getenv("TZ", "America/Sao_Paulo"))
WHATSAPP_URL = "https://web.whatsapp.com/"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["login", "capture"])
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--session-dir", default="whatsapp_session")
    parser.add_argument("--output", default="work/whatsapp_unread_today.json")
    parser.add_argument("--screenshot", default="outputs/whatsapp-login.png")
    args = parser.parse_args()

    if args.mode == "login":
        await login(args)
    else:
        await capture(args)


async def browser_context(session_dir):
    from playwright.async_api import async_playwright

    chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    playwright = await async_playwright().start()
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=session_dir,
        executable_path=chrome_bin,
        headless=True,
        viewport={"width": 1280, "height": 900},
        locale="pt-BR",
        timezone_id=os.getenv("TZ", "America/Sao_Paulo"),
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,900",
        ],
    )
    context._playwright_handle = playwright
    return context


async def close_context(context):
    playwright = getattr(context, "_playwright_handle", None)
    await context.close()
    if playwright:
        await playwright.stop()


async def login(args):
    Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)
    context = await browser_context(args.session_dir)
    page = context.pages[0] if context.pages else await context.new_page()
    try:
        await page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
        deadline = dt.datetime.now(dt.timezone.utc).timestamp() + args.timeout
        print(f"Abra/baixe {args.screenshot} e escaneie o QR Code pelo WhatsApp.")
        print("Vou atualizar a imagem a cada poucos segundos ate o login completar.")
        while dt.datetime.now(dt.timezone.utc).timestamp() < deadline:
            if await is_logged_in(page):
                await page.screenshot(path=args.screenshot, full_page=False)
                print("WhatsApp login confirmado. Sessao persistida na VPS.")
                return
            await save_login_screenshot(page, args.screenshot)
            print(f"QR atualizado em {args.screenshot}")
            await page.wait_for_timeout(5000)
        raise SystemExit("Timeout aguardando login do WhatsApp Web.")
    finally:
        await close_context(context)


async def capture(args):
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path("outputs").mkdir(parents=True, exist_ok=True)
    context = await browser_context(args.session_dir)
    page = context.pages[0] if context.pages else await context.new_page()
    try:
        await page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
        deadline = dt.datetime.now(dt.timezone.utc).timestamp() + args.timeout
        while dt.datetime.now(dt.timezone.utc).timestamp() < deadline:
            if await is_logged_in(page):
                break
            await page.wait_for_timeout(2000)
        if not await is_logged_in(page):
            await save_login_screenshot(page, "outputs/whatsapp-login-needed.png")
            write_status("not_logged_in", logged_in=False, error="WhatsApp nao esta logado.")
            raise SystemExit("WhatsApp nao esta logado. Rode: docker compose run --rm whatsapp-login")

        while dt.datetime.now(dt.timezone.utc).timestamp() < deadline:
            if await is_chat_list_ready(page):
                break
            await page.wait_for_timeout(3000)
        if not await is_chat_list_ready(page):
            await page.screenshot(path="outputs/whatsapp-capture-loading.png", full_page=False)
            write_status("loading_timeout", logged_in=True, error="Lista de conversas nao terminou de carregar.")
            raise SystemExit("WhatsApp esta logado, mas a lista de conversas nao terminou de carregar.")

        await dismiss_overlays(page)
        await apply_unread_filter(page)
        await dismiss_overlays(page)
        await page.wait_for_timeout(2500)
        items = await extract_unread_items(page)
        Path(args.output).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        write_status(
            "ok",
            logged_in=True,
            unread_conversations=len(items),
            unread_messages=sum(int(item.get("unread_count") or 1) for item in items),
        )
        await page.screenshot(path="outputs/whatsapp-capture.png", full_page=False)
        print(f"WhatsApp: {len(items)} conversa(s) nao lida(s) capturada(s).")
        print(f"JSON: {args.output}")
    finally:
        await close_context(context)


async def is_logged_in(page):
    return await page.evaluate(
        """() => {
            const text = document.body.innerText || "";
            if (/Use WhatsApp on your computer|Usar o WhatsApp no computador|Log into WhatsApp Web/i.test(text)) {
                return false;
            }
            if (document.querySelector('[aria-label*="Chat list" i], [aria-label*="lista de conversas" i]')) {
                return true;
            }
            if (document.querySelector('div[contenteditable="true"][role="textbox"]')) {
                return true;
            }
            return /Search or start a new chat|Pesquisar ou começar uma nova conversa|Conversas/i.test(text);
        }"""
    )


async def is_chat_list_ready(page):
    return await page.evaluate(
        """() => {
            const text = document.body.innerText || "";
            if (/Carregando suas conversas|Loading your chats|Sincronizando mensagens|Syncing messages/i.test(text)) {
                return false;
            }
            const chatList = document.querySelector('[aria-label*="lista de conversas" i], [aria-label*="chat list" i]');
            const rows = Array.from(document.querySelectorAll('[role="listitem"], [data-testid="cell-frame-container"]'));
            const visibleRows = rows.filter(row => {
                const box = row.getBoundingClientRect();
                return box.width > 200 && box.height > 30 && box.top >= 0;
            });
            return Boolean(chatList) || visibleRows.length > 0 || /Pesquisar ou começar uma nova conversa|Search or start a new chat/i.test(text);
        }"""
    )


async def apply_unread_filter(page):
    clicked = await page.evaluate(
        """() => {
            const controls = Array.from(document.querySelectorAll('button, [role="button"]'));
            const target = controls.find(el => {
                const text = `${el.innerText || ""} ${el.getAttribute("aria-label") || ""}`.trim();
                return /Não lidas|Nao lidas|Unread/i.test(text);
            });
            if (!target) return false;
            target.click();
            return true;
        }"""
    )
    if clicked:
        await page.wait_for_timeout(1200)
    return clicked


async def dismiss_overlays(page):
    for _ in range(3):
        clicked = await page.evaluate(
            """() => {
                const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [aria-modal="true"]'));
                if (!dialogs.length) return false;
                const controls = Array.from(document.querySelectorAll('button, [role="button"]'));
                const close = controls.find(el => {
                    const text = `${el.innerText || ""} ${el.getAttribute("aria-label") || ""} ${el.getAttribute("title") || ""}`.trim();
                    return /Fechar|Close|Dispensar|Agora não|Not now|×|✕/i.test(text);
                }) || controls.find(el => {
                    const box = el.getBoundingClientRect();
                    return box.width >= 20 && box.width <= 70 && box.height >= 20 && box.height <= 70 && box.left > window.innerWidth * 0.55 && box.top < window.innerHeight * 0.45;
                });
                if (!close) return false;
                close.click();
                return true;
            }"""
        )
        if not clicked:
            return False
        await page.wait_for_timeout(800)
    return True


async def save_login_screenshot(page, path):
    selectors = [
        "canvas",
        "[data-testid='qrcode']",
        "[aria-label*='QR' i]",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count():
                box = await locator.bounding_box()
                if box and box.get("width", 0) > 120 and box.get("height", 0) > 120:
                    await locator.screenshot(path=path)
                    return
        except Exception:
            pass
    await page.screenshot(path=path, full_page=False)


async def extract_unread_items(page):
    raw = await page.evaluate(
        """() => {
            const unreadRegex = /(unread|não lida|nao lida|não lidas|nao lidas|mensagens não lidas|mensagens nao lidas)/i;
            const rows = Array.from(document.querySelectorAll('[role="listitem"], [data-testid="cell-frame-container"], [aria-label*="lista de conversas" i] [role="row"], [aria-label*="chat list" i] [role="row"]'));
            const seen = new Set();
            const items = [];
            const timeRegex = /^[0-9]{1,2}:[0-9]{2}$|^ontem$|^yesterday$/i;
            for (const row of rows) {
                const box = row.getBoundingClientRect();
                if (box.width < 200 || box.height < 30) continue;
                const labels = Array.from(row.querySelectorAll('[aria-label]')).map(el => el.getAttribute('aria-label') || '');
                const unreadLabel = labels.find(label => unreadRegex.test(label));
                const text = (row.innerText || '').trim();
                const hasUnreadText = unreadRegex.test(text);
                const badgeText = Array.from(row.querySelectorAll('span, div'))
                    .map(el => (el.innerText || '').trim())
                    .find(value => /^[0-9]{1,3}$/.test(value));
                if (!unreadLabel && !hasUnreadText && !badgeText) continue;

                const lines = text.split('\\n').map(line => line.trim()).filter(Boolean);
                if (!lines.length) continue;
                const contentLines = lines.filter(line => {
                    if (unreadRegex.test(line)) return false;
                    if (/^[0-9]{1,3}$/.test(line)) return false;
                    if (timeRegex.test(line)) return false;
                    if (/^(Tudo|All|Não lidas|Nao lidas|Unread|Grupos|Groups)$/i.test(line)) return false;
                    return true;
                });
                const contact = contentLines[0] || lines.find(line => !unreadRegex.test(line)) || lines[0];
                const key = contact.toLowerCase();
                if (seen.has(key)) continue;
                seen.add(key);

                const countSource = unreadLabel || badgeText || text;
                const countMatch = String(countSource).match(/[0-9]{1,3}/);
                const unreadCount = countMatch ? Number(countMatch[0]) : 1;
                const timeLine = lines.find(line => timeRegex.test(line)) || '';
                const preview = contentLines.find((line, idx) => {
                    if (line === contact) return false;
                    if (line === timeLine) return false;
                    return true;
                }) || '';

                items.push({ contact, time: timeLine, unread_count: unreadCount, preview });
            }
            return items.slice(0, 30);
        }"""
    )
    now = dt.datetime.now(TIMEZONE)
    normalized = []
    for item in raw:
        contact = clean_text(item.get("contact", ""))
        if not contact:
            continue
        normalized.append(
            {
                "contact": contact,
                "time": clean_text(item.get("time")) or now.strftime("%H:%M"),
                "unread_count": int(item.get("unread_count") or 1),
                "preview": clean_text(item.get("preview", "")),
            }
        )
    return normalized


def clean_text(value):
    return re.sub(r"\\s+", " ", str(value or "")).strip()


def write_status(status, **extra):
    Path("outputs").mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "captured_at": dt.datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        **extra,
    }
    Path("outputs/whatsapp-status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
