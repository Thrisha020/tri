# # ### 🧠 Tool Execution Strategy

# # # This project supports both single-tool and multi-tool GitHub automation:

# # # | Type           | Agent Used          | File                          |
# # # |----------------|---------------------|-------------------------------|
# # # | Single Tool    | `MCPAgent`          | `github_client.py`           |
# # # | Tool Chaining  | `LangGraph BigTool` | `tool_chaining.py`            |

# # # - **LangGraph BigTool Agent** is ONLY used inside `tool_chaining.py`
# # # - If a user query includes multiple actions (e.g., "create branch AND create file"), it is routed to the BigTool agent.

import asyncio
import os
import uuid
from typing import List, Dict, Any, Optional, Literal, TypedDict, Annotated
from dotenv import load_dotenv
from langchain_fireworks import ChatFireworks
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain.tools import BaseTool
from langchain_community.embeddings import HuggingFaceEmbeddings
from langgraph.graph import StateGraph, START, END
from langgraph.store.memory import InMemoryStore
from langgraph.store.base import BaseStore
from langgraph.prebuilt import InjectedStore
from rich.console import Console
from typing_extensions import Annotated
from mcp_use import MCPAgent, MCPClient
from g_server_new import get_tool_registry

console = Console()
load_dotenv()

class AgentState(TypedDict):
    """Acts like memory for LangGraph nodes."""
    messages: List[Any] # stores All messages so far
    current_query: str # The user's current request
    selected_tools: List[str] # Which tools were picked
    tool_results: Dict[str, Any] # The results from those tools 
    final_response: str # The final answer from the AI 
    iteration_count: int # How many steps have been run 
    max_iterations: int # How many steps have been run 
    is_complex_query: bool # Whether it's a multi-step request

class GitHubLangGraphAgent:
    """This is your main client-side agent that:
        Connects to the MCP server.
        Gets the tool list.
        Builds and runs the LangGraph pipeline.
        Returns the AI's final output."""
    
    def __init__(self, tools: Dict[str, BaseTool], client: MCPClient):
        """
        Saves the tool registry and MCP client.
        Loads HuggingFace embeddings for tool matching.
        Sets up an in-memory store for tool metadata.
        Gets the LLM connection.
        Placeholder for the LangGraph graph.
        """
        self.tool_registry = tools
        self.client = client
        self.embeddings = HuggingFaceEmbeddings()
        self.store = self._initialize_store()
        self.llm = self._get_llm()
        self.graph = None
        
    def _initialize_store(self) -> InMemoryStore:
        """Creates an InMemoryStore with your embeddings.
            This store helps match queries to tools semantically."""
        store = InMemoryStore(
            index={
                "embed": self.embeddings,
                "dims": 384,
                "fields": ["description"],
            }
        )
        for tool_name, tool in self.tool_registry.items():
            store.put(
                ("tools",),
                tool_name,
                {"description": f"{tool.name}: {tool.description}"},
            )
        return store
    
    def _get_llm(self):
        """Initialize the language model"""
        return ChatFireworks(
            model="accounts/fireworks/models/qwen3-235b-a22b-instruct-2507",
            max_tokens=36000,
        )
    
    def _retrieve_relevant_tools(
        self,
        query: str,
        store: Annotated[BaseStore, InjectedStore],
        limit: int = 5
    ) -> List[str]:
        """Retrieve relevant tools based on the query with GitHub-specific handling"""
        results = store.search(("tools",), query=query, limit=limit)
        tool_names = [result.key for result in results]
        
        # Special handling for common GitHub operations
        query_lower = query.lower()
        special_tools = {
                "repository": ["create_repository", "delete_repository", "get_repository_info"],
                "repo": ["create_repository", "delete_repository", "get_repository_info"],
                "branch": ["list_branches", "create_branch", "delete_branch", "checkout_branch"],
                "file": ["create_file", "update_file", "delete_file", "create_local_file"],
                "pull request": ["list_pull_requests", "create_pull_request", "merge_pull_request", "close_pull_request"],
                "pr": ["list_pull_requests", "create_pull_request", "merge_pull_request", "close_pull_request"],
                "issue": ["list_issues", "create_issue", "close_issue", "comment_on_issue"],
                "clone": ["clone_repository", "get_repo_status", "pull_changes"],
                "commit": ["commit_changes", "push_changes", "get_repo_status"],
                "workflow": ["list_workflows", "trigger_workflow"],
                "collaborator": ["list_collaborators", "add_collaborator"],
                "user": ["get_github_user_info", "list_user_repositories"],
                "organization": ["list_organization_repositories"],
                "vscode": ["open_file_in_vscode"]
            }
        
        for keyword, tools in special_tools.items():
            if keyword in query_lower:
                for tool in tools:
                    if tool not in tool_names and tool in self.tool_registry:
                        tool_names.append(tool)
        
        return tool_names[:limit]
    
    # Node Functions
    def query_analysis_node(self, state: AgentState) -> AgentState:
        """Analyze the user query and determine relevant tools
        This node identifies the nature of the query and selects appropriate tools."""

        console.print(f"[blue]🔍 Analyzing query: {state['current_query']}[/blue]")
        
        # Check for complex queries (containing "and", "then", etc.)
        complex_indicators = [" and ", " then ", " after ", " next "]
        is_complex = any(indicator in state["current_query"].lower() 
                      for indicator in complex_indicators)
        
        # Retrieve relevant tools
        selected_tools = self._retrieve_relevant_tools(
            state["current_query"], 
            store=self.store
        )
        
        console.print(f"[cyan]🔧 Selected tools: {selected_tools}[/cyan]")
        
        return {
            **state,
            "selected_tools": selected_tools,
            "iteration_count": 0,
            "max_iterations": 5 if is_complex else 10,
            "is_complex_query": is_complex
        }
    
    async def tool_execution_node(self, state: AgentState) -> AgentState:
        """Execute the selected tools with intelligent planning,This is where the actual work happens – e.g., cloning a repo,"""
        console.print("[green]⚙️ Executing tools...[/green]")
        
        tool_results = state["tool_results"].copy()
        messages = state["messages"].copy()
        
        # Build context
        context = ""
        if tool_results:
            context = "\nPrevious executions:\n"
            for tool_name, result in tool_results.items():
                context += f"- {tool_name}: {str(result)[:200]}...\n"
            context += "\nBased on these results, determine next steps.\n"
        
        planning_prompt = f"""
        You are a GitHub automation assistant. User asked: "{state['current_query']}"
        
        Available tools: {', '.join(state['selected_tools'])}
        Current iteration: {state['iteration_count'] + 1}/{state['max_iterations']}
        
        {context}
        
        Guidelines:
        - If user mentions setting or switching repository, use 'set_repository' tool first
        - Execute ONE tool at a time
        - If something doesn't exist but is needed, create it
        - Get information before acting when needed
        - Think step-by-step about the user's goal
        - Always set repository before performing operations if not already set
        
        What tool should you execute next?
        """
        
        messages.append(HumanMessage(content=planning_prompt))
        
        llm_with_tools = self.llm.bind_tools([
            self.tool_registry[tool_name] for tool_name in state["selected_tools"]
        ])
        
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                console.print(f"[yellow]🔧 Calling {tool_name} with args: {tool_args}[/yellow]")
                
                try:
                    if tool_name in self.tool_registry:
                        # Use async invocation
                        tool = self.tool_registry[tool_name]
                        if hasattr(tool, 'ainvoke'):
                            result = await tool.ainvoke(tool_args)
                        else:
                            result = await asyncio.get_event_loop().run_in_executor(
                                None, tool.invoke, tool_args
                            )
                        tool_results[tool_name] = result
                        
                        messages.append(ToolMessage(
                            content=str(result),
                            tool_call_id=tool_call["id"]
                        ))
                        
                        console.print(f"[green]✅ Tool {tool_name} result: {result[:200]}...[/green]")
                    else:
                        error_msg = f"Tool {tool_name} not found"
                        tool_results[tool_name] = error_msg
                        console.print(f"[red]❌ {error_msg}[/red]")
                        
                except Exception as e:
                    error_msg = f"Error executing {tool_name}: {str(e)}"
                    tool_results[tool_name] = error_msg
                    console.print(f"[red]❌ {error_msg}[/red]")
        else:
            console.print("[yellow]⚠️ No tool calls in LLM response[/yellow]")
        
        return {
            **state,
            "messages": messages,
            "tool_results": tool_results,
            "iteration_count": state["iteration_count"] + 1
        }
    
    async def response_generation_node(self, state: AgentState) -> AgentState:
        """Generate final response based on tool results,Final step before returning to user."""
        console.print("[blue]📝 Generating final response...[/blue]")
        
        summary_text = "No tools executed." if not state["tool_results"] else "\n".join(
            f"**{name}**: {result}" for name, result in state["tool_results"].items()
        )
        
        final_prompt = f"""
        User asked: "{state['current_query']}"
        
        Executed actions:
        {summary_text}
        
        Provide a response that:
        1. Summarizes what was done
        2. Answers the original question
        3. Includes relevant details
        4. Uses markdown formatting
        5. Explains if more work is needed
        """
        
        messages = state["messages"].copy()
        messages.append(HumanMessage(content=final_prompt))
        
        final_response = await self.llm.ainvoke(messages)
        
        return {
            **state,
            "final_response": final_response.content,
            "messages": messages + [final_response]
        }
    
    def should_continue(self, state: AgentState) -> Literal["tool_execution", "response_generation"]:
        """Decision node for continuing execution,Decision node to check if the workflow needs to loop."""

        if state["iteration_count"] >= state["max_iterations"]:
            console.print(f"[yellow]⚠️ Reached max iterations ({state['max_iterations']})[/yellow]")
            return "response_generation"
        
        if not state["tool_results"]:
            return "tool_execution"
        
        messages = state["messages"]
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, 'content') and last_message.content:
                content_lower = str(last_message.content).lower()
                continue_indicators = [
                    "next", "then", "now i will", "i need to", "let me", 
                    "should", "will now", "going to", "need to check"
                ]
                if any(indicator in content_lower for indicator in continue_indicators):
                    console.print("[cyan]🔄 LLM indicates more work needed...[/cyan]")
                    return "tool_execution"
        
        if state["tool_results"]:
            last_result = str(list(state["tool_results"].values())[-1]).lower()
            incomplete_indicators = [
                "does not exist", "not found", "failed", "error",
                "next step", "need to", "should create", "empty", "no repository selected"
            ]
            if any(indicator in last_result for indicator in incomplete_indicators):
                console.print("[cyan]🔄 Tool result suggests more work needed...[/cyan]") 
                return "tool_execution"
        
        return "response_generation"
    
    def build_graph(self) -> StateGraph:
        """Build the LangGraph workflow, Creates the LangGraph StateGraph that defines the workflow.,This is where you define the flowchart of the agent."""
        workflow = StateGraph(AgentState)
        
        workflow.add_node("query_analysis", self.query_analysis_node)
        workflow.add_node("tool_execution", self.tool_execution_node)
        workflow.add_node("response_generation", self.response_generation_node)
        
        workflow.add_edge(START, "query_analysis")
        workflow.add_edge("query_analysis", "tool_execution")
        workflow.add_conditional_edges(
            "tool_execution",
            self.should_continue,
            {
                "tool_execution": "tool_execution",
                "response_generation": "response_generation"
            }
        )
        workflow.add_edge("response_generation", END)
        
        return workflow.compile()
    
    def initialize_agent(self):
        """Initialize the LangGraph agent"""
        self.graph = self.build_graph()
        return self.graph

async def main():
    """Main function to run the GitHub LangGraph agent"""
    # MCP Client configuration
    config = {
        "mcpServers": {
            "github_server": {
                "command": "python",
                "args": ["/Users/thrisham/Desktop/cobol_code/github_actions/MCP_4/g_client_new.py"]
            }
        }
    }
    
    console.print("[blue]🚀 Starting MCP client...[/blue]")
    client = MCPClient.from_dict(config)
    
    # Initialize LLM
    os.environ["FIREWORKS_API_KEY"] = "fw_3ZPF2zBvheEvfSGRRoChVZPc"
    llm = ChatFireworks(
        model="accounts/fireworks/models/qwen3-235b-a22b-instruct-250",
        max_tokens=8192,
    )
# accounts/fireworks/models/qwen3-235b-a22b-instruct-250
# accounts/fireworks/models/qwen3-235b-a22b-thinking-2507
    # Initialize agent
    console.print("[blue]⏳ Initializing GitHub LangGraph Agent...[/blue]")
    tools = get_tool_registry()  # Make sure this imports your GitHub tools
    agent = GitHubLangGraphAgent(tools, client)
    agent.initialize_agent()
    
    console.print("[bold green]🧠 GitHub LangGraph Agent is ready![/bold green]")
    console.print("[yellow]Available operations:[/yellow]")
    console.print("• Repository management (set/create/delete/get info)")
    console.print("• Branch management (create/delete/list/checkout)")
    console.print("• File operations (create/update/delete)")
    console.print("• Pull requests (create/list/merge/close)")
    console.print("• Issues (create/list/close/comment)")
    console.print("• Repository cloning and local git operations")
    console.print("• Collaborator management")
    console.print("• Workflow operations")
    console.print("\n[bold cyan]📍 Repository Setup:[/bold cyan]")
    console.print("• Start by setting a repository: 'set repository test-folder'")
    console.print("• Or create a new repository: 'create repository my-new-repo'")
    console.print("\nType 'exit' to quit.")

    # Initialize state properly
    state = {
        "messages": [],
        "current_query": "",
        "selected_tools": [],
        "tool_results": {},
        "final_response": "",
        "iteration_count": 0,
        "max_iterations": 5,
        "is_complex_query": False
    }

    while True:
        user_query = input("\n🔍 Enter your query: ").strip()
        if user_query.lower() in ('exit', 'quit', 'bye'):
            break

        console.print(f"\n[bold]Processing: {user_query}[/bold]")
        console.print("─" * 50)

        # Reset state for new query
        state = {
            "messages": [HumanMessage(content=user_query)],
            "current_query": user_query,
            "selected_tools": [],
            "tool_results": {},
            "final_response": "",
            "iteration_count": 0,
            "max_iterations": 5,  # Increased to allow for repository setting + operations
            "is_complex_query": False
        }

        try:
            result_state = await agent.graph.ainvoke(state)
            console.print(f"\n[green]📋 Result:[/green]\n{result_state['final_response']}")
        except Exception as e:
            console.print(f"[red]❌ Error: {str(e)}[/red]")

        console.print("─" * 50)

    try:
        await client.close_all_sessions()
    except:
        pass

if __name__ == "__main__":
    asyncio.run(main())



# python3 /Users/thrisham/Desktop/cobol_code/github_actions/MCP_4/g_client_new.py