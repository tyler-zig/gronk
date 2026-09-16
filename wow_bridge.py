import argparse
import asyncio
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from xai_sdk import AsyncClient as XAIAsyncClient
from xai_sdk.chat import system as xai_system
from xai_sdk.chat import user as xai_user


LOGGER = logging.getLogger("GronkWoWBridge")

TABLE_RE = re.compile(r"\{(?P<body>[^{}]*)\}", re.DOTALL)
KEY_VALUE_RE = re.compile(r"(?P<key>\w+)\s*=\s*\"(?P<value>(?:\\.|[^\"])*)\"")
RESPONSE_ID_RE = re.compile(r"requestId\s*=\s*\"((?:\\.|[^\"])*)\"")

SYSTEM_PROMPT = """You are Grok answering a World of Warcraft chat question.
Keep replies short enough for in-game chat. Be useful, direct, and avoid spam.
If the question is about current WoW information that may have changed, say when you are unsure.
Do not include markdown tables."""


def lua_unescape(value: str) -> str:
    return (
        value.replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
    )


def lua_string(value: str) -> str:
    value = value or ""
    return '"' + value.replace("\\", r"\\").replace('"', r"\"").replace("\r", r"\r").replace("\n", r"\n") + '"'


def parse_requests(lua_text: str) -> list[dict]:
    requests = []
    for table_match in TABLE_RE.finditer(lua_text):
        fields = {
            match.group("key"): lua_unescape(match.group("value"))
            for match in KEY_VALUE_RE.finditer(table_match.group("body"))
        }
        required = {"id", "prompt", "channelType", "channelName", "author", "status"}
        if required.issubset(fields) and fields["status"] == "pending":
            request = {
                "id": fields["id"],
                "prompt": fields["prompt"],
                "channel_type": fields["channelType"],
                "channel_name": fields["channelName"],
                "author": fields["author"],
                "status": fields["status"],
            }
            requests.append(request)
    return requests


def parse_response_ids(lua_text: str) -> set[str]:
    return {lua_unescape(match.group(1)) for match in RESPONSE_ID_RE.finditer(lua_text)}


def find_saved_variables_path() -> Path | None:
    configured = os.getenv("WOW_GRONK_SAVED_VARIABLES")
    if configured:
        return Path(configured).expanduser()

    home = Path.home()
    candidates = list(home.glob("**/World of Warcraft/_retail_/WTF/Account/*/SavedVariables/Gronk.lua"))
    candidates.extend(home.glob("**/World of Warcraft/_anniversary_/WTF/Account/*/SavedVariables/Gronk.lua"))
    candidates.extend(home.glob("**/World of Warcraft/_classic_/WTF/Account/*/SavedVariables/Gronk.lua"))
    return candidates[0] if candidates else None


async def ask_grok(client: XAIAsyncClient, model: str, request: dict) -> str:
    chat = client.chat.create(
        model=model,
        messages=[
            xai_system(SYSTEM_PROMPT),
            xai_user(
                "WoW chat context:\n"
                f"- Author: {request['author']}\n"
                f"- Channel type: {request['channel_type']}\n"
                f"- Channel name: {request['channel_name']}\n\n"
                f"Question: {request['prompt']}"
            ),
        ],
        store_messages=False,
    )
    response = await chat.sample()
    return (response.content or "").strip()


def response_to_lua(request: dict, answer: str) -> str:
    return (
        "{ "
        f"requestId = {lua_string(request['id'])}, "
        f"answer = {lua_string(answer)}, "
        f"channelType = {lua_string(request['channel_type'])}, "
        f"channelName = {lua_string(request['channel_name'])}, "
        "delivered = false "
        "}"
    )


def append_responses(lua_text: str, responses: list[str]) -> str:
    if not responses:
        return lua_text

    if "responses" not in lua_text:
        insertion = "\n    responses = {\n        " + ",\n        ".join(responses) + "\n    },"
        return lua_text.replace("GronkDB = {", "GronkDB = {" + insertion, 1)

    match = re.search(r"responses\s*=\s*\{", lua_text)
    if not match:
        raise ValueError("Could not find GronkDB.responses table in SavedVariables")

    insert_at = match.end()
    existing_body_start = lua_text[insert_at:]
    prefix = "\n        " + ",\n        ".join(responses)
    if existing_body_start.lstrip().startswith("}"):
        prefix += "\n    "
    else:
        prefix += ","
    return lua_text[:insert_at] + prefix + lua_text[insert_at:]


async def run_once(saved_variables: Path, model: str) -> int:
    if not saved_variables.exists():
        LOGGER.warning("SavedVariables file does not exist yet: %s", saved_variables)
        return 0

    lua_text = saved_variables.read_text(encoding="utf-8", errors="replace")
    existing_response_ids = parse_response_ids(lua_text)
    pending = [request for request in parse_requests(lua_text) if request["id"] not in existing_response_ids]

    if not pending:
        LOGGER.info("No pending Gronk requests found.")
        return 0

    client = XAIAsyncClient()
    rendered_responses = []
    for request in pending:
        LOGGER.info("Answering %s from %s", request["id"], request["author"])
        try:
            answer = await ask_grok(client, model, request)
        except Exception as exc:
            LOGGER.exception("Grok request failed for %s", request["id"])
            answer = f"Gronk bridge error: {exc}"
        rendered_responses.append(response_to_lua(request, answer))

    updated = append_responses(lua_text, rendered_responses)

    # Back up the original file before overwriting
    backup_path = saved_variables.with_suffix(saved_variables.suffix + '.bak')
    try:
        backup_path.write_text(lua_text, encoding='utf-8')
        LOGGER.info('Backed up original SavedVariables to %s', backup_path)
    except Exception:
        LOGGER.warning('Could not back up SavedVariables to %s', backup_path)

    saved_variables.write_text(updated, encoding="utf-8")
    LOGGER.info("Wrote %s response(s). Use /reload in WoW to load them.", len(rendered_responses))
    return len(rendered_responses)


async def run_loop(saved_variables: Path, model: str, interval: int) -> None:
    while True:
        await run_once(saved_variables, model)
        await asyncio.sleep(interval)


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Bridge WoW Gronk SavedVariables requests to xAI Grok.")
    parser.add_argument("--saved-variables", help="Path to WTF/Account/<account>/SavedVariables/Gronk.lua")
    parser.add_argument("--model", default=os.getenv("GROK_TEXT_MODEL", "grok-4.3"))
    parser.add_argument("--watch", action="store_true", help="Keep polling for newly saved requests.")
    parser.add_argument("--interval", type=int, default=5, help="Polling interval in seconds for --watch.")
    args = parser.parse_args()

    saved_variables = Path(args.saved_variables).expanduser() if args.saved_variables else find_saved_variables_path()
    if not saved_variables:
        raise SystemExit("Could not find Gronk.lua. Pass --saved-variables or set WOW_GRONK_SAVED_VARIABLES.")

    if args.watch:
        asyncio.run(run_loop(saved_variables, args.model, args.interval))
    else:
        asyncio.run(run_once(saved_variables, args.model))


if __name__ == "__main__":
    main()
