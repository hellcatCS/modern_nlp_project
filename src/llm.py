import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from src.config import settings
from src.functions import TOOLS
from src.prompts import build_system_prompt

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, restaurant):
        self.restaurant = restaurant
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key
        )
        self.llm_with_tools = llm.bind_tools(TOOLS)
        self.tools_by_name = {t.name: t for t in TOOLS}

    def _convert_history(self, messages: list[dict]) -> list:
        system_prompt = build_system_prompt(self.restaurant)
        result = [SystemMessage(content=system_prompt)]
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
        response = self.llm_with_tools.invoke(lc_messages)

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

            response = self.llm_with_tools.invoke(lc_messages)

        return response.content, escalated
