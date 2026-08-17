#!/usr/bin/env python3
import base64
import datetime as dt
import html
import subprocess
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo


SERVICE = "chief-of-staff-exchange"
ACCOUNT = "eu@eduardocastro.com.br"
SERVER = "east.EXCH025.serverdata.net"
EWS_URL = f"https://{SERVER}/EWS/Exchange.asmx"
TIMEZONE = ZoneInfo("America/Sao_Paulo")
OUT_DIR = Path("work/billfish_reports")
NS = {
    "s": "http://schemas.xmlsoap.org/soap/envelope/",
    "m": "http://schemas.microsoft.com/exchange/services/2006/messages",
    "t": "http://schemas.microsoft.com/exchange/services/2006/types",
}


def keychain_password():
    result = subprocess.run(
        ["security", "find-generic-password", "-a", ACCOUNT, "-s", SERVICE, "-w"],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Senha nao encontrada no Keychain.")
    return result.stdout.rstrip("\n")


def ews_request(password, body_xml):
    envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
  <s:Header><t:RequestServerVersion Version="Exchange2013" /></s:Header>
  <s:Body>{body_xml}</s:Body>
</s:Envelope>"""
    token = base64.b64encode(f"{ACCOUNT}:{password}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(EWS_URL, data=envelope.encode("utf-8"), method="POST")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "text/xml; charset=utf-8")
    req.add_header("Accept", "text/xml")
    req.add_header("User-Agent", "ChiefOfStaffDigital/1.0")
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"EWS HTTP {exc.code}: {detail}") from exc


def text(node, path, default=""):
    found = node.find(path, NS)
    return found.text if found is not None and found.text is not None else default


def parse_time(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TIMEZONE)


def find_billfish_messages(password):
    folders = find_all_folders(password)
    messages = []
    for folder in folders:
        messages.extend(find_billfish_messages_in_folder(password, folder))
    return sorted(messages, key=lambda item: item["received"] or dt.datetime.min.replace(tzinfo=TIMEZONE), reverse=True)


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
    folders = []
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


def find_billfish_messages_in_folder(password, folder):
    body = """
<m:FindItem Traversal="Shallow">
  <m:ItemShape>
    <t:BaseShape>Default</t:BaseShape>
    <t:AdditionalProperties>
      <t:FieldURI FieldURI="item:DateTimeReceived" />
      <t:FieldURI FieldURI="item:HasAttachments" />
      <t:FieldURI FieldURI="item:Attachments" />
      <t:FieldURI FieldURI="item:TextBody" />
      <t:FieldURI FieldURI="item:Body" />
    </t:AdditionalProperties>
  </m:ItemShape>
  <m:IndexedPageItemView MaxEntriesReturned="80" Offset="0" BasePoint="Beginning" />
  <m:Restriction>
    <t:Contains ContainmentMode="Substring" ContainmentComparison="IgnoreCase">
      <t:FieldURI FieldURI="item:Subject" />
      <t:Constant Value="BILLFISH FIA" />
    </t:Contains>
  </m:Restriction>
  <m:ParentFolderIds>
    <t:FolderId Id="__FOLDER_ID__" />
  </m:ParentFolderIds>
  <m:SortOrder>
    <t:FieldOrder Order="Descending">
      <t:FieldURI FieldURI="item:DateTimeReceived" />
    </t:FieldOrder>
  </m:SortOrder>
</m:FindItem>""".replace("__FOLDER_ID__", html.escape(folder["id"]))
    root = ET.fromstring(ews_request(password, body))
    messages = []
    for msg in root.findall(".//t:Message", NS):
        item_id = msg.find("t:ItemId", NS)
        attachments = []
        for att in msg.findall(".//t:FileAttachment", NS):
            att_id = att.find("t:AttachmentId", NS)
            attachments.append(
                {
                    "name": text(att, "t:Name"),
                    "id": att_id.attrib.get("Id", "") if att_id is not None else "",
                }
            )
        messages.append(
            {
                "subject": text(msg, "t:Subject"),
                "received": parse_time(text(msg, "t:DateTimeReceived")),
                "folder": folder["name"],
                "body": text(msg, "t:TextBody") or text(msg, "t:Body"),
                "item_id": item_id.attrib.get("Id", "") if item_id is not None else "",
                "attachments": attachments,
            }
        )
    return messages


def download_attachment(password, attachment_id, filename):
    body = f"""
<m:GetAttachment>
  <m:AttachmentShape />
  <m:AttachmentIds>
    <t:AttachmentId Id="{html.escape(attachment_id)}" />
  </m:AttachmentIds>
</m:GetAttachment>"""
    root = ET.fromstring(ews_request(password, body))
    content = text(root, ".//t:Content")
    if not content:
        raise RuntimeError(f"No content for attachment {filename}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / safe_filename(filename)
    path.write_bytes(base64.b64decode(content))
    return path


def get_item_details(password, item_id):
    body = f"""
<m:GetItem>
  <m:ItemShape>
    <t:BaseShape>AllProperties</t:BaseShape>
    <t:IncludeMimeContent>true</t:IncludeMimeContent>
  </m:ItemShape>
  <m:ItemIds>
    <t:ItemId Id="{html.escape(item_id)}" />
  </m:ItemIds>
</m:GetItem>"""
    root = ET.fromstring(ews_request(password, body))
    msg = root.find(".//t:Message", NS)
    if msg is None:
        return {}
    attachments = []
    for att in msg.findall(".//t:FileAttachment", NS):
        att_id = att.find("t:AttachmentId", NS)
        attachments.append(
            {
                "name": text(att, "t:Name"),
                "id": att_id.attrib.get("Id", "") if att_id is not None else "",
            }
        )
    return {
        "body": text(msg, "t:Body"),
        "mime": text(msg, "t:MimeContent"),
        "attachments": attachments,
    }


def safe_filename(value):
    return "".join(ch if ch.isalnum() or ch in ".-_ " else "_" for ch in value).strip() or "attachment.pdf"


def main():
    password = keychain_password()
    messages = find_billfish_messages(password)
    print(f"found_messages={len(messages)}")
    for i, msg in enumerate(messages[:10], 1):
        if i <= 6:
            details = get_item_details(password, msg["item_id"])
            if details:
                msg["body"] = details.get("body", msg.get("body", ""))
                msg["mime"] = details.get("mime", "")
                msg["attachments"] = details.get("attachments", msg["attachments"])
        print(f"{i}. {msg['received']} | {msg['subject']} | attachments={len(msg['attachments'])}")
        for att in msg["attachments"]:
            print(f"   - {att['name']}")
        if i <= 2:
            print((msg.get("body") or "")[:1200].replace("\n", " ")[:1200])
            print((msg.get("mime") or "")[:600].replace("\n", " ")[:600])
    downloaded = []
    for msg in messages[:6]:
        for att in msg["attachments"]:
            if att["name"].lower().endswith(".pdf"):
                downloaded.append(download_attachment(password, att["id"], att["name"]))
    for path in downloaded:
        print(f"downloaded={path}")


if __name__ == "__main__":
    sys.exit(main())
