"""
Stream AI Message Sender - gRPC client for SSH chat AI integration.

This service connects to the SSH chat server via gRPC, receives chat messages,
and streams AI responses from Google Gemini back to the chat.
"""

import argparse
import asyncio
import json
import logging
import os
import random
import struct
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional

import grpc
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from proto import middleware_pb2, middleware_pb2_grpc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_gemini_client_configs(config_path_str: Optional[str] = None) -> tuple[list[dict], Path]:
    """Load Gemini client configuration entries from a JSON or JSONL file."""
    default_path = Path(__file__).parent / 'conf' / 'participants.json'
    config_path = Path(config_path_str) if config_path_str else default_path

    if not config_path.exists():
        raise FileNotFoundError(f"Client configuration file not found: {config_path}")

    try:
        if config_path.suffix.lower() == '.jsonl':
            entries = []
            with open(config_path, 'r', encoding='utf-8') as fh:
                for line_number, line in enumerate(fh, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    entries.append(json.loads(stripped))
        else:
            with open(config_path, 'r', encoding='utf-8') as fh:
                entries = json.load(fh)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in %s: %s", config_path, exc)
        raise

    if not isinstance(entries, list):
        raise ValueError(f"Client configuration in {config_path} must be a list")

    required_fields = {"model_name", "nick", "prompt", "temperature", "max_output_tokens"}
    configs: list[dict] = []

    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            raise TypeError(f"Entry #{index + 1} in {config_path} is not an object")

        missing = required_fields - raw_entry.keys()
        if missing:
            raise KeyError(f"Entry #{index + 1} in {config_path} missing fields: {', '.join(sorted(missing))}")

        prompt_value = raw_entry.get('prompt', '')
        if isinstance(prompt_value, list):
            prompt_text = "\n".join(str(line) for line in prompt_value)
        elif isinstance(prompt_value, str):
            prompt_text = prompt_value
        else:
            raise TypeError(
                f"Entry #{index + 1} in {config_path} has unsupported prompt type: {type(prompt_value).__name__}"
            )

        configs.append(
            {
                'model_name': str(raw_entry['model_name']),
                'nick': str(raw_entry['nick']),
                'prompt': prompt_text,
                'temperature': float(raw_entry['temperature']),
                'max_output_tokens': int(raw_entry['max_output_tokens']),
            }
        )

    return configs, config_path


def load_response_probability(env_value: Optional[str]) -> float:
    """Parse service-wide response probability from an environment value."""
    default = 1.0
    if not env_value:
        return default

    tokens = [token.strip() for token in env_value.split(',') if token.strip()]
    if not tokens:
        logger.warning("No valid response probability parsed; falling back to default")
        return default

    first_token = tokens[0]
    try:
        value = float(first_token)
    except ValueError:
        logger.warning("Invalid response probability '%s'; falling back to default", first_token)
        return default

    clamped = max(0.0, min(value, 1.0))
    if len(tokens) > 1:
        logger.info(
            "Multiple response probabilities provided; using the first value %.2f for service-wide probability",
            clamped,
        )

    return clamped


class GeminiClient:
    """Wrapper for Google Gemini client with model name and nickname."""
    
    def __init__(
        self,
        api_key: str,
        model_name: str = 'gemini-2.5-flash',
        nick: str = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
        max_output_tokens: int = 2048,
    ):
        """
        Initialize Gemini client wrapper.
        
        Args:
            api_key: Google Gemini API key
            model_name: Model name (e.g., 'gemini-2.5-flash')
            nick: Nickname for the AI (defaults to model_name if not provided)
            system_prompt: System instruction for the AI personality
            temperature: Sampling temperature for the model
            max_output_tokens: Maximum output tokens allowed per response
        """
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.nick = nick if nick else model_name
        self.system_prompt = system_prompt or ""
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.index = 0
        logger.info(
            "Gemini client initialized - Model: %s, Nick: %s, Temp: %.2f, Max tokens: %d",
            self.model_name,
            self.nick,
            self.temperature,
            self.max_output_tokens,
        )


async def get_public_ipv4() -> str:
    """Fetch the external public IPv4 address."""
    # Try multiple services in case one fails
    services = [
        "https://api.ipify.org?format=text",
        "https://api4.ipify.org",
        "https://checkip.amazonaws.com",
        "https://icanhazip.com",
    ]
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        for service in services:
            try:
                response = await client.get(service)
                if response.status_code == 200:
                    ip = response.text.strip()
                    logger.info(f"Public IPv4 address: {ip}")
                    return ip
            except Exception as e:
                logger.warning(f"Failed to get IP from {service}: {e}")
                continue
    
    raise RuntimeError("Failed to get public IPv4 address from all services")


class AIMessageSender:
    """Manages gRPC connection and AI message streaming."""
    
    def __init__(
        self,
        server_address: str,
        gemini_clients: list[GeminiClient],
        use_tls: bool = False,
        use_auth: bool = False,
        private_key_path: Optional[Path | str] = None,
        server_cert_path: Optional[Path | str] = None,
        tls_target_name: Optional[str] = None,
        response_probability: float = 1.0,
    ):
        self.server_address = server_address
        self.gemini_clients = gemini_clients  # List of multiple clients
        self.ai_nicks = {client.nick for client in gemini_clients}
        self.use_tls = use_tls
        self.use_auth = use_auth
        self.tls_target_name = tls_target_name
        self.public_ip = None  # Will be fetched asynchronously
        self.response_probability = max(0.0, min(response_probability, 1.0))
        self.private_key = None
        self.server_cert_path = server_cert_path
        
        # Load private key for authentication if needed
        if self.use_auth:
            if not private_key_path:
                raise ValueError("Private key path required when authentication is enabled")
            
            self.private_key_path = Path(private_key_path)
            if not self.private_key_path.exists():
                raise FileNotFoundError(f"Private key not found: {self.private_key_path}")

            with self.private_key_path.open('rb') as f:
                self.private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None
                )
            logger.info(f"Loaded private key from {self.private_key_path} for authentication")
        else:
            logger.info("Signature-based authentication is disabled")

        # Load server certificate for TLS if needed
        if self.use_tls:
            if server_cert_path:
                self.server_cert_path = Path(server_cert_path)
                if not self.server_cert_path.exists():
                    logger.warning(
                        f"gRPC server certificate not found at {self.server_cert_path}, will use system root certificates"
                    )
                    self.server_cert_path = None
                else:
                    logger.info(f"Will use TLS with certificate from {self.server_cert_path}")
            else:
                logger.warning("No server certificate path provided, will use system root certificates")
                self.server_cert_path = None
        else:
            logger.info("TLS is disabled (insecure connection)")
        
        # Throttling: track last AI request time
        self.last_ai_request_time = 0
        self.throttle_seconds = 0.5  # Wait at least 0.5 seconds between AI calls
        self.is_processing = {}  # Track processing state per client
        for client in gemini_clients:
            self.is_processing[client.nick] = False
        
        # Message history for context (keep last 200 messages)
        self.message_history = deque(maxlen=200)
        
        # Queue for pending AI requests (per client)
        self.pending_ai_requests = {}
        self.client_enabled = {}
        self.client_index_map = {}
        for index, client in enumerate(gemini_clients, start=1):
            client.index = index
            self.pending_ai_requests[client.nick] = asyncio.Queue()
            self.client_enabled[client.nick] = True
            self.client_index_map[index] = client

        # Response distribution tracking for fairness
        self.response_counts = {client.nick: 0 for client in gemini_clients}

        self.info_nick = 'ai-info'
        self.info_builders: list[Callable[[], str]] = [
            lambda: "AI 제어 명령: /ai on <index>, /ai off <index> (인덱스 확인: /ai list)",
            lambda: f"AI 응답률: {self.response_probability * 100:.0f}%",
            lambda: f"AI 응답률이 100%면 모든 메시지에 AI가 답변합니다. 단, 모든 AI가 응답을 생성 중일 때 전송한 메시지는 보류된 후 이후 응답 처리에 함께 반영됩니다.",
            lambda: f"매우 낮은 확률로 복수의 AI가 동시에 답변합니다.",
            lambda: "활성 AI: " + (", ".join(self._get_active_client_names()) if self._get_active_client_names() else "없음"),
        ]
        self.info_interval_seconds = max(60.0, float(os.getenv('INFO_MESSAGE_INTERVAL', '180')))
        self.info_rotation_index = 0
        self.info_loop_resume_event = asyncio.Event()
        self.info_loop_resume_event.set()
        self.info_loop_paused = False

        logger.info(
            "AIMessageSender initialized - Service response probability: %.2f",
            self.response_probability,
        )

    @staticmethod
    def _preview(text: str, limit: int) -> str:
        """Return a text preview, adding ellipsis only when truncated."""
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    def _extract_retry_delay_seconds(self, payload: Any) -> Optional[float]:
        candidate_details = None
        if isinstance(payload, dict):
            if 'details' in payload:
                candidate_details = payload['details']
            elif 'error' in payload and isinstance(payload['error'], dict):
                candidate_details = payload['error'].get('details')

        if not isinstance(candidate_details, list):
            return None

        for detail in candidate_details:
            if not isinstance(detail, dict):
                continue
            if detail.get('@type') != 'type.googleapis.com/google.rpc.RetryInfo':
                continue

            retry_delay = detail.get('retryDelay')
            seconds_value: Optional[float] = None

            if isinstance(retry_delay, str):
                value = retry_delay.strip().lower()
                if value.endswith('s'):
                    value = value[:-1]
                try:
                    seconds_value = float(value)
                except ValueError:
                    continue
            elif isinstance(retry_delay, dict):
                seconds_raw = retry_delay.get('seconds')
                nanos_raw = retry_delay.get('nanos', 0)
                try:
                    seconds_component = float(seconds_raw) if seconds_raw is not None else 0.0
                    nanos_component = float(nanos_raw) / 1_000_000_000
                    seconds_value = seconds_component + nanos_component
                except (TypeError, ValueError):
                    continue
            elif isinstance(retry_delay, (int, float)):
                seconds_value = float(retry_delay)

            if seconds_value is not None:
                return seconds_value

        return None

    def _build_api_error_text(self, api_error: genai_errors.APIError) -> str:
        status = (api_error.status or "").upper()
        message_headline = (api_error.message or "").split('\n', 1)[0].strip()

        if status == 'RESOURCE_EXHAUSTED' or api_error.code == 429:
            retry_seconds = self._extract_retry_delay_seconds(api_error.details)
            if retry_seconds:
                wait_seconds = max(1, int(round(retry_seconds)))
                return f"지금 쿼터 제한 때문에 잠깐 멈춰야 해. 약 {wait_seconds}초 뒤에 다시 물어봐줘!"
            return "지금 쿼터 제한에 걸려서 답변을 못해. 잠시 후에 다시 요청해줘!"

        if status == 'UNAVAILABLE':
            return "지금 Gemini 서비스에 연결이 안 돼. 조금 후에 다시 시도해볼게!"

        if status == 'DEADLINE_EXCEEDED':
            return "응답이 너무 오래 걸려서 중단됐어. 다시 한 번 시도해줘!"

        if message_headline:
            return f"지금 오류가 있어서 답변하기 어렵네: {message_headline}"

        return "지금은 잠깐 문제가 생겨서 답변을 못했어. 조금 뒤에 다시 시도해줘!"

    def _alternate_model_names(self, base_client: GeminiClient) -> list[str]:
        unique_models: list[str] = []
        for candidate in self.gemini_clients:
            if candidate.nick == base_client.nick:
                continue
            if candidate.model_name == base_client.model_name:
                continue
            if candidate.model_name not in unique_models:
                unique_models.append(candidate.model_name)
        return unique_models

    def _resolve_model_for_attempt(
        self,
        base_client: GeminiClient,
        alt_models: list[str],
        attempt_index: int,
    ) -> str:
        if alt_models and attempt_index % 2 == 0:
            alt_position = (attempt_index // 2) - 1
            if alt_position < 0:
                alt_position = 0
            alt_index = alt_position % len(alt_models)
            return alt_models[alt_index]
        return base_client.model_name

    async def _emit_error_message(
        self,
        response_queue: asyncio.Queue,
        gemini_client: GeminiClient,
        message_id: str,
        text: str,
    ) -> None:
        response = middleware_pb2.AIResponse(
            message_id=message_id,
            text=text,
            is_final=True,
            nick=gemini_client.nick,
            ip=self.public_ip or "",
        )
        await response_queue.put(response)
        self.message_history.append(f"[{gemini_client.nick}]: {text}")
    
    def create_auth_signature(self) -> tuple[bytes, int, str]:
        """Create authentication signature for IP + timestamp."""
        if not self.use_auth:
            return b"", 0, ""
        
        if not self.public_ip:
            raise RuntimeError("Public IP not initialized")
        
        if not self.private_key:
            raise RuntimeError("Private key not loaded")
        
        # Create timestamp in milliseconds
        timestamp = int(time.time() * 1000)
        
        # Create message (IP bytes + 8 bytes timestamp in big endian)
        ip_bytes = self.public_ip.encode('utf-8')
        timestamp_bytes = struct.pack('>Q', timestamp)
        message = ip_bytes + timestamp_bytes
        
        # Sign the message using ECDSA
        signature = self.private_key.sign(
            message,
            ec.ECDSA(hashes.SHA256())
        )
        
        logger.info(f"Created auth signature for IP {self.public_ip} and timestamp {timestamp}")
        return signature, timestamp, self.public_ip

    def _client_load(self, client: GeminiClient) -> int:
        """Compute a lightweight load metric for a client."""
        queue_size = self.pending_ai_requests[client.nick].qsize()
        processing = 1 if self.is_processing.get(client.nick) else 0
        return queue_size + processing

    def _should_trigger_response(self) -> bool:
        """Decide if the service should respond based on its probability."""
        roll = random.random()
        if roll <= self.response_probability:
            return True

        logger.debug(
            "Service skipped response due to probability %.2f (roll=%.2f)",
            self.response_probability,
            roll,
        )
        return False

    def _active_clients(self) -> list[GeminiClient]:
        return [client for client in self.gemini_clients if self.client_enabled.get(client.nick, True)]

    def _get_client_by_index(self, index: int) -> Optional[GeminiClient]:
        return self.client_index_map.get(index)

    def _set_client_enabled(self, client: GeminiClient, enabled: bool) -> int:
        previous = self.client_enabled.get(client.nick, True)
        self.client_enabled[client.nick] = enabled
        dropped = 0
        if not enabled:
            queue = self.pending_ai_requests[client.nick]
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                    dropped += 1
                except asyncio.QueueEmpty:
                    break
            if dropped:
                logger.info("Cleared %d pending requests for %s after deactivation", dropped, client.nick)
        elif not previous:
            logger.info("%s re-enabled", client.nick)
        return dropped

    def _format_client_status(self, client: GeminiClient) -> str:
        state = "ON" if self.client_enabled.get(client.nick, True) else "OFF"
        return f"{client.nick}(state: {state}, model: {client.model_name}, index: {client.index})"

    def _get_active_client_names(self) -> list[str]:
        return [client.nick for client in self._active_clients()]

    def _generate_info_message(self) -> Optional[str]:
        if not self.info_builders:
            return None

        builder = self.info_builders[self.info_rotation_index % len(self.info_builders)]
        self.info_rotation_index = (self.info_rotation_index + 1) % len(self.info_builders)
        return builder()

    async def _send_system_message(self, response_queue: asyncio.Queue, text: str, *, is_final: bool = True) -> None:
        if not text:
            return

        message_id = f"info-{int(time.time() * 1000)}"
        response = middleware_pb2.AIResponse(
            message_id=message_id,
            text=text,
            is_final=is_final,
            nick=self.info_nick,
            ip=self.public_ip or "",
        )
        await response_queue.put(response)
        self.message_history.append(f"[{self.info_nick}]: {text}")

    def _is_user_nick(self, nick: str) -> bool:
        return nick not in self.ai_nicks and nick not in {self.info_nick, 'server'}

    def _recent_manual_info_stats(self, window: int = 35) -> tuple[int, int]:
        recent_entries = list(self.message_history)[-window:]
        manual_count = 0
        user_count = 0

        for entry in recent_entries:
            if not entry.startswith('['):
                continue
            closing_index = entry.find(']:')
            if closing_index == -1:
                continue
            nick = entry[1:closing_index]

            if nick == self.info_nick:
                manual_count += 1
            elif self._is_user_nick(nick):
                user_count += 1

        return manual_count, user_count

    def _should_pause_info_loop(self) -> bool:
        threshold = len(self.info_builders) if self.info_builders else 1
        manual_count, user_count = self._recent_manual_info_stats()
        return manual_count >= threshold and user_count == 0

    def _register_user_activity(self, nick: str) -> None:
        if not self._is_user_nick(nick):
            return

        if not self.info_loop_resume_event.is_set():
            self.info_loop_resume_event.set()
            if self.info_loop_paused:
                logger.info("User activity detected; resuming info message loop")

    async def handle_control_command(self, message, response_queue: asyncio.Queue) -> bool:
        text = message.text.strip()
        parts = text.split()
        if not parts or parts[0].lower() != '/ai':
            return False

        if message.nick in self.ai_nicks or message.nick == self.info_nick:
            return False

        logger.info("Control command from %s: %s", message.nick, text)

        if len(parts) == 1:
            await self._send_system_message(response_queue, "사용법: /ai on <index>, /ai off <index>, /ai list")
            return True

        action = parts[1].lower()

        if action == 'list':
            status_line = ", ".join(self._format_client_status(client) for client in self.gemini_clients)
            await self._send_system_message(response_queue, f"AI 목록: {status_line}")
            return True

        if action in {'on', 'off'}:
            if len(parts) < 3:
                await self._send_system_message(response_queue, "인덱스를 함께 적어주세요. 예) /ai on 1")
                return True

            try:
                index = int(parts[2])
            except ValueError:
                await self._send_system_message(response_queue, "인덱스는 숫자로 입력해주세요.")
                return True

            client = self._get_client_by_index(index)
            if not client:
                await self._send_system_message(response_queue, f"인덱스 {index}번 AI는 없습니다.")
                return True

            enable_flag = action == 'on'
            if self.client_enabled.get(client.nick, True) == enable_flag:
                state_text = "이미 켜져 있습니다." if enable_flag else "이미 꺼져 있습니다."
                await self._send_system_message(response_queue, f"{client.index}번 {client.nick}가 {state_text}")
                return True

            dropped = self._set_client_enabled(client, enable_flag)
            if enable_flag:
                await self._send_system_message(response_queue, f"{client.index}번 {client.nick}가 활성화되었습니다.")
            else:
                suffix = f" ({dropped}개 대기중 메시지 취소)" if dropped else ""
                await self._send_system_message(response_queue, f"{client.index}번 {client.nick}가 비활성화되었습니다.{suffix}")
            return True

        await self._send_system_message(response_queue, "알 수 없는 명령입니다. /ai list로 상태를 확인해주세요.")
        return True

    async def info_message_loop(self, response_queue: asyncio.Queue) -> None:
        try:
            while True:
                await asyncio.sleep(self.info_interval_seconds)

                if self._should_pause_info_loop():
                    if not self.info_loop_paused:
                        self.info_loop_paused = True
                        self.info_loop_resume_event.clear()
                        logger.info("Pausing manual info messages until user activity resumes")
                    await self.info_loop_resume_event.wait()
                    self.info_loop_paused = False
                    self.info_loop_resume_event.clear()
                    continue

                text = self._generate_info_message()
                if not text:
                    continue
                await self._send_system_message(response_queue, text)
        except asyncio.CancelledError:
            logger.debug("Info message loop cancelled")
            return

    def select_clients_for_message(self, message_text: str, nickname: str) -> list[GeminiClient]:
        """Determine which Gemini clients should respond to the incoming message."""
        if nickname in self.ai_nicks or nickname == 'server':
            return []

        active_clients = self._active_clients()
        if not active_clients:
            return []

        message_lower = message_text.lower()
        current_time = time.time()

        # Identify explicit mentions which skip throttling
        forced_candidates = [
            client for client in active_clients
            if f'@{client.nick.lower()}' in message_lower
        ]
        selected_clients: set[GeminiClient] = set(forced_candidates)

        if not forced_candidates and not self._should_trigger_response():
            return []

        desired_count = len(selected_clients) if selected_clients else 1
        if not selected_clients:
            # Inject simultaneous response probabilities
            roll = random.random()
            if roll < 0.05:
                desired_count = min(3, len(active_clients))
            elif roll < 0.15:
                desired_count = min(2, len(active_clients))

        remaining_candidates = [client for client in active_clients if client not in selected_clients]
        if remaining_candidates and len(selected_clients) < desired_count:
            # Sort by fairness (response count) then current load, random tie-breaker
            ordered_candidates = sorted(
                remaining_candidates,
                key=lambda c: (
                    self.response_counts[c.nick],
                    self._client_load(c),
                    random.random()
                )
            )
            for candidate in ordered_candidates:
                if len(selected_clients) >= desired_count:
                    break
                selected_clients.add(candidate)

        selected_list = list(selected_clients)
        if selected_list:
            self.last_ai_request_time = current_time

        return selected_list
    
    async def generate_ai_response(
        self, 
        message_id: str, 
        message_text: str,
        nickname: str,
        gemini_client: GeminiClient,
        response_queue: asyncio.Queue
    ):
        """Generate AI response using Gemini streaming."""
        try:
            self.is_processing[gemini_client.nick] = True
            self.last_ai_request_time = time.time()
            
            # Recent message context already captured in message_history by the main loop
            preview = self._preview(message_text, 50)
            logger.info(f"[{gemini_client.nick}] Generating AI response for message: {preview}")
            
            # Build contents with message history for context
            contents = []
            # Add recent message history (last 200 messages including AI responses)
            recent_history = list(self.message_history)[:-1]  # Exclude current message
            if recent_history:
                history_text = "\n".join(recent_history)
                contents.append(f"Recent conversation:\n{history_text}\n\nCurrent message: [{nickname}]: {message_text}")
            else:
                contents.append(f"[{nickname}]: {message_text}")
            alt_models = self._alternate_model_names(gemini_client)
            max_attempts = max(1, 2 * len(alt_models) + 1)
            attempt_index = 0

            while attempt_index < max_attempts:
                attempt_index += 1
                model_to_use = self._resolve_model_for_attempt(gemini_client, alt_models, attempt_index)

                if attempt_index > 1:
                    logger.info(
                        "[%s] Retry attempt %d/%d using model %s (primary: %s)",
                        gemini_client.nick,
                        attempt_index,
                        max_attempts,
                        model_to_use,
                        gemini_client.model_name,
                    )

                # Configure generation per attempt to avoid state carryover
                config = types.GenerateContentConfig(
                    temperature=gemini_client.temperature,
                    max_output_tokens=gemini_client.max_output_tokens,
                    system_instruction=gemini_client.system_prompt,
                )

                accumulated_text: str = ""
                prompt_block_feedback: Optional[types.GenerateContentResponsePromptFeedback] = None
                usage_metadata: Optional[types.GenerateContentResponseUsageMetadata] = None
                finish_reason: Optional[types.FinishReason] = None
                finish_message: Optional[str] = None
                function_calls_detected: list[types.FunctionCall] = []
                received_binary_part = False
                chunk_count = 0
                last_sent_len = 0

                try:
                    # Use async streaming with configurable model
                    stream = await gemini_client.client.aio.models.generate_content_stream(
                        model=model_to_use,
                        contents=contents,
                        config=config
                    )

                    async for chunk in stream:
                        if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                            prompt_block_feedback = chunk.prompt_feedback
                            logger.warning(
                                "Prompt blocked by safety filter: %s - %s",
                                prompt_block_feedback.block_reason,
                                prompt_block_feedback.block_reason_message,
                            )
                            break

                        if chunk.usage_metadata:
                            usage_metadata = chunk.usage_metadata

                        if chunk.function_calls:
                            function_calls_detected.extend(chunk.function_calls)

                        if not chunk.candidates:
                            continue

                        candidate = chunk.candidates[0]
                        if candidate.finish_reason:
                            finish_reason = candidate.finish_reason
                        if candidate.finish_message:
                            finish_message = candidate.finish_message

                        new_text_fragments: list[str] = []

                        if candidate.content and candidate.content.parts:
                            for part in candidate.content.parts:
                                if part.text:
                                    if part.thought:
                                        continue
                                    logger.debug(f"Received text chunk: {part.text}")
                                    new_text_fragments.append(part.text)
                                elif part.function_call:
                                    function_calls_detected.append(part.function_call)
                                    logger.info(
                                        "Model requested function call: %s",
                                        part.function_call.name,
                                    )
                                elif part.function_response:
                                    logger.info("Received function response chunk; ignoring for chat output")
                                elif part.inline_data or part.file_data:
                                    received_binary_part = True
                                    logger.info("Received non-text part in stream; ignoring for chat output")
                                elif part.executable_code or part.code_execution_result:
                                    logger.info("Received code execution content; ignoring for chat output")

                        if not new_text_fragments:
                            continue

                        new_text = "".join(new_text_fragments)
                        if not new_text:
                            continue

                        accumulated_text += new_text
                        chunk_count += 1

                        if (
                            chunk_count == 1
                            or chunk_count % 2 == 0
                            or len(accumulated_text) - last_sent_len >= 60
                        ):
                            response = middleware_pb2.AIResponse(
                                message_id=message_id,
                                text=accumulated_text,
                                is_final=False,
                                nick=gemini_client.nick,
                                ip=self.public_ip
                            )
                            await response_queue.put(response)
                            last_sent_len = len(accumulated_text)

                    if usage_metadata:
                        logger.info(
                            "Token usage - prompt: %s, response: %s, total: %s",
                            usage_metadata.prompt_token_count,
                            usage_metadata.candidates_token_count,
                            usage_metadata.total_token_count,
                        )

                    if finish_reason and finish_reason not in (
                        types.FinishReason.FINISH_REASON_UNSPECIFIED,
                        types.FinishReason.STOP,
                    ):
                        logger.info("Stream finished early: %s (%s) [model=%s]", finish_reason, finish_message, model_to_use)

                    final_text = accumulated_text

                    if prompt_block_feedback and prompt_block_feedback.block_reason:
                        final_text = "이 질문은 정책 때문에 막혔어. 다른 방법으로 물어봐줘!"
                    elif not final_text.strip():
                        if function_calls_detected:
                            final_text = "지금은 도구 호출을 하려는 중이라 답변이 어려워. 다른 질문으로 가보자!"
                        elif received_binary_part:
                            final_text = "이미지나 파일을 보내려고 했는데 아직 처리 못 해. 다른 얘기 해볼까?"
                        else:
                            final_text = "이번엔 답변을 제대로 못 만들었어. 다시 한번만 물어봐줘!"

                    response = middleware_pb2.AIResponse(
                        message_id=message_id,
                        text=final_text,
                        is_final=True,
                        nick=gemini_client.nick,
                        ip=self.public_ip
                    )
                    await response_queue.put(response)
                    self.response_counts[gemini_client.nick] += 1
                    self.message_history.append(f"[{gemini_client.nick}]: {final_text}")
                    logger.info(
                        "[%s] AI response complete using model %s: %s",
                        gemini_client.nick,
                        model_to_use,
                        self._preview(final_text, 100),
                    )
                    return

                except genai_errors.APIError as api_error:
                    is_quota_error = (
                        api_error.code == 429
                        or (api_error.status or "").upper() == 'RESOURCE_EXHAUSTED'
                    )

                    if (
                        is_quota_error
                        and alt_models
                        and attempt_index < max_attempts
                        and chunk_count == 0
                        and not accumulated_text.strip()
                    ):
                        next_attempt = attempt_index + 1
                        next_model = self._resolve_model_for_attempt(gemini_client, alt_models, next_attempt)
                        logger.warning(
                            "[%s] Quota hit on model %s (attempt %d/%d). Retrying with model %s.",
                            gemini_client.nick,
                            model_to_use,
                            attempt_index,
                            max_attempts,
                            next_model,
                        )
                        continue

                    raise
        except genai_errors.APIError as api_error:
            friendly_text = self._build_api_error_text(api_error)
            logger.warning(
                "[%s] Gemini API error %s %s: %s",
                gemini_client.nick,
                api_error.code,
                api_error.status,
                self._preview(api_error.message or "", 120),
            )
            logger.debug("[%s] Gemini API error payload: %s", gemini_client.nick, api_error.details)
            await self._emit_error_message(response_queue, gemini_client, message_id, friendly_text)
        except Exception as e:
            logger.error(f"[{gemini_client.nick}] Error generating AI response: {e}", exc_info=True)
            fallback_text = "지금은 오류가 생겨서 답변을 못했어. 잠시 후 다시 시도해줘!"
            await self._emit_error_message(response_queue, gemini_client, message_id, fallback_text)
        finally:
            self.is_processing[gemini_client.nick] = False
    
    async def ai_response_worker(self, gemini_client: GeminiClient, response_queue: asyncio.Queue):
        """Worker to process AI response requests from a queue for a specific client."""
        client_queue = self.pending_ai_requests[gemini_client.nick]
        
        while True:
            # Wait for a request to come into the queue
            message_id, message_text, nickname = await client_queue.get()

            if not self.client_enabled.get(gemini_client.nick, True):
                client_queue.task_done()
                continue
            
            # Wait until this specific AI is not processing another request
            while self.is_processing[gemini_client.nick]:
                await asyncio.sleep(0.1)
            
            # Now process the request
            await self.generate_ai_response(
                message_id,
                message_text,
                nickname,
                gemini_client,
                response_queue
            )
            client_queue.task_done()

    async def run(self):
        """Main loop: connect to gRPC server and handle messages."""
        # Fetch public IP address if authentication is enabled
        if self.use_auth:
            try:
                self.public_ip = await get_public_ipv4()
            except Exception as e:
                logger.error(f"Failed to get public IP (required for authentication): {e}")
                return
        else:
            self.public_ip = ""
            logger.info("Authentication disabled")
        
        # Setup channel credentials based on security mode
        credentials = None
        channel_options = [
            # Keepalive settings for 24/7 connection stability
            ('grpc.keepalive_time_ms', 30000),  # Send keepalive ping every 30 seconds
            ('grpc.keepalive_timeout_ms', 10000),  # Wait 10 seconds for keepalive response
            ('grpc.keepalive_permit_without_calls', 1),  # Allow keepalive pings even without active calls
            ('grpc.http2.max_pings_without_data', 0),  # Allow unlimited pings without data
            ('grpc.http2.min_time_between_pings_ms', 10000),  # Minimum 10 seconds between pings
            ('grpc.http2.min_ping_interval_without_data_ms', 5000),  # Minimum 5 seconds without data
        ]

        if self.use_tls:
            # Load TLS credentials - use custom cert if available, otherwise use system root certificates
            server_cert = None
            if self.server_cert_path and self.server_cert_path.exists():
                with self.server_cert_path.open('rb') as f:
                    server_cert = f.read()
                logger.info("Loaded gRPC server certificate chain from %s", self.server_cert_path)
            else:
                logger.warning(
                    "Server certificate not found at %s, using system root certificates",
                    self.server_cert_path if self.server_cert_path else "(not specified)"
                )
            
            credentials = grpc.ssl_channel_credentials(
                root_certificates=server_cert
            )

            if self.tls_target_name:
                channel_options.extend([
                    ('grpc.ssl_target_name_override', self.tls_target_name),
                    ('grpc.default_authority', self.tls_target_name),
                ])
        
        # Connect with infinite retry logic for 24/7 operation
        retry_delay = 5
        attempt = 0
        
        while True:  # Infinite retry loop
            attempt += 1
            try:
                security_mode = "TLS" if self.use_tls else "insecure"
                auth_mode = "with auth" if self.use_auth else "without auth"
                logger.info(
                    f"Connecting to gRPC server at {self.server_address} ({security_mode}, {auth_mode}) (attempt {attempt})"
                )
                
                if self.use_tls and self.tls_target_name:
                    logger.info(f"TLS target name override: {self.tls_target_name}")
                
                # Create channel based on security mode
                if self.use_tls:
                    channel = grpc.aio.secure_channel(
                        self.server_address,
                        credentials,
                        options=channel_options
                    )
                else:
                    channel = grpc.aio.insecure_channel(
                        self.server_address,
                        options=channel_options
                    )

                async with channel:
                    stub = middleware_pb2_grpc.StreamMiddlewareStub(channel)
                    
                    # Queue for responses to send
                    response_queue = asyncio.Queue()

                    # Start AI response workers for each client as background tasks
                    worker_tasks = []
                    for client in self.gemini_clients:
                        task = asyncio.create_task(self.ai_response_worker(client, response_queue))
                        worker_tasks.append(task)
                        logger.info(f"Started worker for {client.nick}")

                    info_task = asyncio.create_task(self.info_message_loop(response_queue))
                    background_tasks = worker_tasks + [info_task]

                    # Flag to track if first message (with auth) has been sent
                    auth_sent = False

                    # Start bidirectional streaming
                    async def response_generator():
                        """Generate responses to send to server."""
                        nonlocal auth_sent

                        # Send initial authentication messages for each client if auth is enabled
                        if self.use_auth and not auth_sent:
                            signature, timestamp, ip = self.create_auth_signature()
                            for client in self.gemini_clients:
                                auth_message = middleware_pb2.AIResponse(
                                    message_id="",  # Empty for auth-only message
                                    text="",
                                    is_final=False,
                                    auth_signature=signature,
                                    auth_timestamp=timestamp,
                                    nick=client.nick,
                                    ip=ip
                                )
                                logger.info(f"Sending initial authentication message for {client.nick}")
                                yield auth_message
                            auth_sent = True

                        # Then continuously process response queue
                        try:
                            while True:
                                response = await response_queue.get()
                                # Set IP in all responses (may be dummy if auth disabled)
                                # if not response.ip:
                                #     response.ip = self.public_ip
                                yield response
                        except asyncio.CancelledError:
                            logger.debug("Response generator cancelled")
                            return

                    call = stub.StreamChat(response_generator())

                    logger.info("Connected to gRPC server!")

                    try:
                        # Process incoming messages
                        async for message in call:
                            logger.info(f"Received message from {message.nick}: {self._preview(message.text, 50)}")

                            record = f"[{message.nick}]: {message.text}"
                            self.message_history.append(record)
                            self._register_user_activity(message.nick)

                            if await self.handle_control_command(message, response_queue):
                                continue

                            selected_clients = self.select_clients_for_message(message.text, message.nick)
                            if selected_clients:
                                logger.info(
                                    "Selected responders: %s",
                                    ", ".join(client.nick for client in selected_clients)
                                )

                            for client in selected_clients:
                                message_id = f"ai-{client.nick}-{int(time.time() * 1000)}"
                                await self.pending_ai_requests[client.nick].put(
                                    (message_id, message.text, message.nick)
                                )
                                logger.info(
                                    "%s queued response (queue=%d)",
                                    client.nick,
                                    self.pending_ai_requests[client.nick].qsize()
                                )
                    finally:
                        for task in background_tasks:
                            task.cancel()
                        await asyncio.gather(*background_tasks, return_exceptions=True)
                
            except grpc.aio.AioRpcError as e:
                logger.error(f"gRPC error: {e.code()} - {e.details()}")
                logger.info(f"Retrying in {retry_delay} seconds")
                await asyncio.sleep(retry_delay)
                # Exponential backoff (max 60 seconds)
                retry_delay = min(retry_delay * 1.5, 60)
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                logger.info(f"Retrying in {retry_delay} seconds")
                await asyncio.sleep(retry_delay)
                # Exponential backoff (max 60 seconds)
                retry_delay = min(retry_delay * 1.5, 60)


async def main():
    """Entry point."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='AI Message Sender - gRPC client for SSH chat')
    parser.add_argument(
        '--grpc-security',
        choices=['none', 'tls'],
        default=None,
        help='gRPC security mode: none (insecure), tls (server cert verification)'
    )
    parser.add_argument(
        '--grpc-auth',
        action='store_true',
        help='Enable signature-based authentication (requires private key)'
    )
    parser.add_argument(
        '--server',
        default=None,
        help='gRPC server address (default: from env GRPC_SERVER_ADDRESS or localhost:3333)'
    )
    args = parser.parse_args()

    loop = asyncio.get_running_loop()
    logger.info("Running event loop: %s", type(loop).__name__)

    # Load .env file if it exists (for local development)
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded environment variables from {env_path}")
    else:
        logger.info("No .env file found, using system environment variables")
    
    # Determine security mode
    security_mode = args.grpc_security
    use_tls = security_mode == 'tls'
    
    # Determine auth mode
    use_auth = args.grpc_auth
    
    # Get configuration from environment
    server_address = os.getenv('GRPC_SERVER_ADDRESS', 'localhost:3333')
    gemini_api_key = os.getenv('GEMINI_API_KEY')

    app_root = Path(__file__).parent
    default_certs_dir = app_root / 'certs'
    certs_dir_env = os.getenv('CERTS_DIR')
    certs_dir = Path(certs_dir_env).expanduser() if certs_dir_env else default_certs_dir

    private_key_path_env = os.getenv('PRIVATE_KEY_PATH')
    private_key_path = (
        Path(private_key_path_env).expanduser()
        if private_key_path_env else certs_dir / 'ai_grpc_client.key'
    ) if use_auth else None

    server_cert_path_env = os.getenv('GRPC_SERVER_CERT_CHAIN_PATH')
    server_cert_path = (
        Path(server_cert_path_env).expanduser()
        if server_cert_path_env else certs_dir / 'grpc_server.cert'
    ) if use_tls else None

    tls_target_name = os.getenv('GRPC_TLS_TARGET_NAME') if use_tls else None
    
    if not gemini_api_key:
        logger.error("GEMINI_API_KEY environment variable not set!")
        logger.error("Please set it: export GEMINI_API_KEY='your-api-key'")
        return
    
    logger.info("Starting AI Message Sender setup")
    logger.info(f"Server: {server_address}")
    logger.info(f"Security mode: {'TLS' if use_tls else 'none (insecure)'}")
    logger.info(f"Authentication: {'enabled' if use_auth else 'disabled'}")
    
    if use_tls:
        logger.info(f"TLS target name: {tls_target_name if tls_target_name else '(not set)'}")
        logger.info(f"Server certificate chain: {server_cert_path}")
    
    if use_auth:
        logger.info(f"Private key: {private_key_path}")
    
    config_override = os.getenv('GEMINI_CLIENT_CONFIG_PATH')
    try:
        client_configs, config_path = load_gemini_client_configs(config_override)
    except Exception as exc:
        logger.error("Failed to load Gemini client configuration: %s", exc)
        return

    if not client_configs:
        logger.error("No Gemini client definitions found in %s", config_path)
        return

    logger.info("Loaded %d Gemini client definitions from %s", len(client_configs), config_path)

    probability_env = os.getenv('AI_RESPONSE_PROBABILITY')
    response_probability = load_response_probability(probability_env)
    logger.info("Service response probability configured: %.2f", response_probability)

    gemini_clients = [
        GeminiClient(
            api_key=gemini_api_key,
            model_name=config['model_name'],
            nick=config['nick'],
            system_prompt=config['prompt'],
            temperature=config['temperature'],
            max_output_tokens=config['max_output_tokens'],
        )
        for config in client_configs
    ]

    logger.info("Starting AI Message Sender with %d AI clients", len(gemini_clients))
    
    sender = AIMessageSender(
        server_address,
        gemini_clients,
        use_tls=use_tls,
        use_auth=use_auth,
        private_key_path=private_key_path,
        server_cert_path=server_cert_path,
        tls_target_name=tls_target_name,
        response_probability=response_probability,
    )
    await sender.run()


if __name__ == "__main__":
    if os.name != "nt":
        try:
            import uvloop  # type: ignore

            uvloop.install()
            logger.info("uvloop event loop policy installed")
        except ImportError:
            logger.warning("uvloop is not installed; falling back to default asyncio event loop")
    else:
        logger.info("Windows detected; using default asyncio event loop policy")

    policy = asyncio.get_event_loop_policy()
    logger.info("Event loop policy in use: %s", policy.__class__.__name__)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
