import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from src.config import settings
from src.functions import TOOLS
from src.knowledge import KnowledgeManager
from src.prompts import build_system_prompt

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, restaurant, knowledge_manager: KnowledgeManager):
        self.restaurant = restaurant
        self.knowledge_manager = knowledge_manager
        primary_llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key
        )
        self.llm_with_tools = primary_llm.bind_tools(TOOLS)
        self.fallback_llm_with_tools = None
        if settings.openrouter_api_key:
            fallback_llm = ChatOpenAI(
                model=settings.openrouter_model,
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
            )
            self.fallback_llm_with_tools = fallback_llm.bind_tools(TOOLS)
        self.tools_by_name = {t.name: t for t in TOOLS}

    def _invoke_with_fallback(self, messages: list):
        try:
            return self.llm_with_tools.invoke(messages)
        except Exception as primary_error:
            if not self.fallback_llm_with_tools:
                raise primary_error
            logger.debug("Primary LLM failed, trying OpenRouter fallback: %s", primary_error)
            return self.fallback_llm_with_tools.invoke(messages)

    def _convert_history(self, messages: list[dict]) -> list:
        system_prompt = build_system_prompt(self.restaurant)
        result = [
            SystemMessage(content=system_prompt),
        ]
        for m in messages:
            if m["role"] == "user":
                result.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                result.append(AIMessage(content=m["content"]))
        return result

    def chat(self, messages: list[dict]) -> tuple[str, bool]:
        lc_messages = self._convert_history(messages)
        escalated = False

        logger.debug(f"Отправка запроса к LLM: {len(messages)} сообщений")
        response = self._invoke_with_fallback(lc_messages)

        while response.tool_calls:
            lc_messages.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                logger.info(f"Вызов функции: {tool_name}")

                tool = self.tools_by_name[tool_name]
                result = tool.invoke(tool_args)

                if "ESCALATED" in result:
                    escalated = True

                lc_messages.append(ToolMessage(content=result, tool_call_id=tool_call["id"]))

            response = self._invoke_with_fallback(lc_messages)

        return response.content, escalated
