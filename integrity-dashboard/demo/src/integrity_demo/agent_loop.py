import json
import logging
import os
import uuid
from typing import List, Dict, Any, Callable

from openai import OpenAI

logger = logging.getLogger("integrity_demo.agent_loop")


class IntegrityAgent:
    """
    Simplified Xibalba-style Agent Loop tailored for the Integrity MVP demo.
    Handles conversation, tool execution, and state management.
    """

    def __init__(self, system_prompt: str, tools: List[Dict[str, Any]], tool_map: Dict[str, Callable], model: str = "gpt-4o-mini"):
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_map = tool_map
        self.model = model
        openai_key = os.getenv("OPENAI_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")
        
        if not openai_key and gemini_key:
            self.client = OpenAI(
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            # Default to gemini-2.5-flash for compatibility if model is default gpt-4o-mini
            if model == "gpt-4o-mini":
                self.model = "gemini-2.5-flash"
        else:
            self.client = OpenAI(api_key=openai_key or gemini_key)

    def run_conversation(self, user_message: str, max_iterations: int = 15) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message}
        ]

        for i in range(max_iterations):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools if self.tools else None,
                tool_choice="auto" if self.tools else "none"
            )

            response_message = response.choices[0].message
            messages.append(response_message.model_dump(exclude_none=True))

            if not response_message.tool_calls:
                # No more tool calls, return final response
                return response_message.content

            # Execute tools
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                logger.info(f"Agent executing tool: {function_name}({function_args})")
                try:
                    if function_name in self.tool_map:
                        function_response = self.tool_map[function_name](**function_args)
                        result_str = json.dumps(function_response) if not isinstance(function_response, str) else function_response
                    else:
                        result_str = f"Error: Tool {function_name} not found."
                except Exception as e:
                    result_str = f"Error executing {function_name}: {str(e)}"
                    logger.error(result_str)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": result_str,
                })

        return "Error: Max iterations reached without a final response."
