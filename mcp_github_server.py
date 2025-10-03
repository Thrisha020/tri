# ======================
# 📦 Purpose & Setup
# ======================
# This script defines the main server logic for GitHub tool automation.
# It exposes a set of @mcp.tool()-decorated functions that represent each available tool.
# These tools can be invoked via an MCP-compatible agent (used by LangChain, BigTool, etc.)
#
# ✅ Supports:
# - Branch management (create, delete, list, checkout)
# - File operations (create, update, delete)
# - Pull requests (create, list, merge, close)
# - Issues management (create, list, close, comment)
# - Repository cloning and local git operations
# - Collaborator management
# - Workflow operations
# - Repository management (create, delete, switch)
# - Independent repository operations (no global state)
# ======================

from mcp.server.fastmcp import FastMCP
import pandas as pd
import yaml
from typing import Any, Optional, List, Dict
import os
import json
import time
import datetime
import sys
from pathlib import Path
import subprocess
# GitHub specific imports
from github import Github
import git
import shutil

# Initialize the MCP server
mcp = FastMCP("github_server")

# Load GitHub configuration
CONFIG_PATH = "/root/amflw_chatbot/jenkins_automate/mcp_c_trial1/github_config.yaml"
with open(CONFIG_PATH, "r") as file:
    config = yaml.safe_load(file)

# GitHub settings
GITHUB_TOKEN = config['github']['token']
DEFAULT_OWNER = config['github']['owner']

# Initialize GitHub object
g = Github(GITHUB_TOKEN)

def get_repo_instance(owner: str, repo_name: str):
    """Get a repository instance"""
    try:
        return g.get_repo(f"{owner}/{repo_name}")
    except Exception as e:
        raise Exception(f"Failed to access repository {owner}/{repo_name}: {str(e)}")

def get_local_repo_path(repo_name: str) -> str:
    """Get local repository path"""
    return f"./{repo_name}"

# ===== ALL MCP TOOLS =====

@mcp.tool()
def github_github_greeter(name: str) -> str:
    """
    A simple tool to greet the user.
    Args:
        name: Name of the user to greet.
    Returns:
        A greeting message.
    """
    return f"Hello, {name}! Welcome to the GitHub automation tool."

@mcp.tool()
async def github_list_branches(owner: str, repo_name: str) -> str:
    """
    List all branches in the repository.
    Args:
        owner: Repository owner (username or organization).
        repo_name: Repository name.
    Returns:
        List of all branch names.
    """
    if not owner or not repo_name:
        return "❌ Missing required parameters: owner, repo_name"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        branches = [branch.name for branch in repo.get_branches()]
        if not branches:
            return "No branches found in repository."
        
        result = ["📋 Repository Branches:"]
        result.extend([f"  • {branch}" for branch in branches])
        result.append(f"\nTotal: {len(branches)} branches")
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error listing branches: {str(e)}"

@mcp.tool()
async def github_create_branch(owner: str, repo_name: str, new_branch: str, base_branch: Optional[str] = "main") -> str:
    """
    Create a new branch from a base branch.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        new_branch: Name of the new branch to create.
        base_branch: Base branch to create from (default: main).
    Returns:
        Status of branch creation.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not new_branch: missing_params.append("new_branch")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        
        # Check if branch already exists
        existing_branches = [branch.name for branch in repo.get_branches()]
        if new_branch in existing_branches:
            return f"❌ Branch '{new_branch}' already exists."
        
        sb = repo.get_branch(base_branch)
        repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=sb.commit.sha)
        return f"✅ Branch '{new_branch}' created successfully from '{base_branch}'."
    except Exception as e:
        return f"❌ Error creating branch: {str(e)}"

@mcp.tool()
async def github_delete_branch(owner: str, repo_name: str, branch_name: str) -> str:
    """
    Delete a branch from the repository.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        branch_name: Name of the branch to delete.
    Returns:
        Status of branch deletion.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not branch_name: missing_params.append("branch_name")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        
        # Don't allow deleting main/master branches
        if branch_name in ['main', 'master']:
            return f"❌ Cannot delete protected branch '{branch_name}'"
        
        ref = repo.get_git_ref(f"heads/{branch_name}")
        ref.delete()
        return f"✅ Branch '{branch_name}' deleted successfully."
    except Exception as e:
        return f"❌ Error deleting branch: {str(e)}"

@mcp.tool()
async def github_create_file(owner: str, repo_name: str, path: str, message: str, content: str, branch: Optional[str] = "main") -> str:
    """
    Create a new file in the repository.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        path: File path where to create the file.
        message: Commit message.
        content: File content.
        branch: Branch to create file on (default: main).
    Returns:
        Status of file creation.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not path: missing_params.append("path")
    if not message: missing_params.append("message")
    if not content: missing_params.append("content")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        repo.create_file(path, message, content, branch=branch)
        return f"✅ File '{path}' created successfully on branch '{branch}'."
    except Exception as e:
        return f"❌ Error creating file: {str(e)}"

@mcp.tool()
async def github_update_file(owner: str, repo_name: str, path: str, message: str, content: str, branch: Optional[str] = "main") -> str:
    """
    Update an existing file in the repository.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        path: File path to update.
        message: Commit message.
        content: New file content.
        branch: Branch to update file on (default: main).
    Returns:
        Status of file update.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not path: missing_params.append("path")
    if not message: missing_params.append("message")
    if not content: missing_params.append("content")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        file = repo.get_contents(path, ref=branch)
        repo.update_file(file.path, message, content, file.sha, branch=branch)
        return f"✅ File '{path}' updated successfully on branch '{branch}'."
    except Exception as e:
        return f"❌ Error updating file: {str(e)}"

@mcp.tool()
async def github_delete_file(owner: str, repo_name: str, path: str, message: str, branch: Optional[str] = "main") -> str:
    """
    Delete a file from the repository.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        path: File path to delete.
        message: Commit message.
        branch: Branch to delete file from (default: main).
    Returns:
        Status of file deletion.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not path: missing_params.append("path")
    if not message: missing_params.append("message")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        file = repo.get_contents(path, ref=branch)
        repo.delete_file(file.path, message, file.sha, branch=branch)
        return f"✅ File '{path}' deleted successfully from branch '{branch}'."
    except Exception as e:
        return f"❌ Error deleting file: {str(e)}"

@mcp.tool()
async def github_list_pull_requests(owner: str, repo_name: str, state: Optional[str] = "open") -> str:
    """
    List pull requests in the repository.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        state: State of pull requests to list (open/closed/all, default: open).
    Returns:
        List of pull requests.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        prs = list(repo.get_pulls(state=state))
        if not prs:
            return f"No {state} pull requests found."
        
        result = [f"{state.title()} Pull Requests:"]
        result.append("-" * 40)
        
        for pr in prs:
            result.append(f"#{pr.number}: {pr.title}")
            result.append(f"  Author: {pr.user.login}")
            result.append(f"  {pr.head.ref} → {pr.base.ref}")
            result.append(f"  URL: {pr.html_url}")
            result.append("")
        
        result.append(f"Total: {len(prs)} pull requests")
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error listing pull requests: {str(e)}"

@mcp.tool()
async def github_create_pull_request(owner: str, repo_name: str, title: str, body: str, head: str, base: Optional[str] = "main") -> str:
    """
    Create a new pull request.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        title: Pull request title.
        body: Pull request description.
        head: Source branch.
        base: Target branch (default: main).
    Returns:
        Status and URL of created pull request.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not title: missing_params.append("title")
    if not body: missing_params.append("body")
    if not head: missing_params.append("head")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)
        return f"✅ Pull request created successfully!\nTitle: {title}\nURL: {pr.html_url}\nNumber: #{pr.number}"
    except Exception as e:
        return f"❌ Error creating pull request: {str(e)}"

@mcp.tool()
async def github_merge_pull_request(owner: str, repo_name: str, pr_number: int) -> str:
    """
    Merge a pull request.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        pr_number: Pull request number to merge.
    Returns:
        Status of pull request merge.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not pr_number: missing_params.append("pr_number")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        pr = repo.get_pull(pr_number)
        pr.merge()
        return f"✅ Pull request #{pr_number} '{pr.title}' merged successfully."
    except Exception as e:
        return f"❌ Error merging pull request: {str(e)}"

@mcp.tool()
async def github_close_pull_request(owner: str, repo_name: str, pr_number: int) -> str:
    """
    Close a pull request without merging.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        pr_number: Pull request number to close.
    Returns:
        Status of pull request closure.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not pr_number: missing_params.append("pr_number")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        pr = repo.get_pull(pr_number)
        pr.edit(state="closed")
        return f"✅ Pull request #{pr_number} '{pr.title}' closed successfully."
    except Exception as e:
        return f"❌ Error closing pull request: {str(e)}"

@mcp.tool()
async def github_list_issues(owner: str, repo_name: str, state: Optional[str] = "open") -> str:
    """
    List issues in the repository.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        state: State of issues to list (open/closed/all, default: open).
    Returns:
        List of issues.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        issues = list(repo.get_issues(state=state))
        if not issues:
            return f"📋 No {state} issues found."
        
        result = [f"{state.title()} Issues:"]
        result.append("-" * 40)
        
        for issue in issues:
            result.append(f"#{issue.number}: {issue.title}")
            result.append(f"  Author: {issue.user.login}")
            result.append(f"  Labels: {', '.join([label.name for label in issue.labels]) or 'None'}")
            result.append(f"  URL: {issue.html_url}")
            result.append("")
        
        result.append(f"Total: {len(issues)} issues")
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error listing issues: {str(e)}"

@mcp.tool()
async def github_create_issue(owner: str, repo_name: str, title: str, body: str) -> str:
    """
    Create a new issue.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        title: Issue title.
        body: Issue description.
    Returns:
        Status and URL of created issue.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not title: missing_params.append("title")
    if not body: missing_params.append("body")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        issue = repo.create_issue(title=title, body=body)
        return f"✅ Issue created successfully!\nTitle: {title}\nURL: {issue.html_url}\nNumber: #{issue.number}"
    except Exception as e:
        return f"❌ Error creating issue: {str(e)}"

@mcp.tool()
async def github_close_issue(owner: str, repo_name: str, issue_number: int) -> str:
    """
    Close an issue.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        issue_number: Issue number to close.
    Returns:
        Status of issue closure.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not issue_number: missing_params.append("issue_number")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        issue = repo.get_issue(number=issue_number)
        issue.edit(state="closed")
        return f"✅ Issue #{issue_number} '{issue.title}' closed successfully."
    except Exception as e:
        return f"❌ Error closing issue: {str(e)}"

@mcp.tool()
async def github_comment_on_issue(owner: str, repo_name: str, issue_number: int, comment: str) -> str:
    """
    Add a comment to an issue or pull request.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        issue_number: Issue or PR number to comment on.
        comment: Comment text.
    Returns:
        Status of comment addition.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not issue_number: missing_params.append("issue_number")
    if not comment: missing_params.append("comment")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        issue = repo.get_issue(number=issue_number)
        issue.create_comment(comment)
        return f"✅ Comment added successfully to issue/PR #{issue_number}."
    except Exception as e:
        return f"❌ Error adding comment: {str(e)}"

@mcp.tool()
async def github_list_collaborators(owner: str, repo_name: str) -> str:
    """
    List repository collaborators.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
    Returns:
        List of collaborators.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        collaborators = list(repo.get_collaborators())
        if not collaborators:
            return "📋 No collaborators found."
        
        result = ["👥 Repository Collaborators:"]
        result.append("-" * 30)
        
        for collab in collaborators:
            result.append(f"  • {collab.login}")
        
        result.append(f"\nTotal: {len(collaborators)} collaborators")
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error listing collaborators: {str(e)}"

@mcp.tool()
async def github_add_collaborator(owner: str, repo_name: str, username: str, permission: Optional[str] = "push") -> str:
    """
    Add a collaborator to the repository.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
        username: GitHub username to add as collaborator.
        permission: Permission level (pull/push/admin, default: push).
    Returns:
        Status of collaborator addition.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    if not username: missing_params.append("username")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        repo.add_to_collaborators(username, permission)
        return f"✅ Collaborator '{username}' added successfully with '{permission}' permission."
    except Exception as e:
        return f"❌ Error adding collaborator: {str(e)}"

@mcp.tool()
async def github_list_workflows(owner: str, repo_name: str) -> str:
    """
    List GitHub Actions workflows.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
    Returns:
        List of workflows.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        workflows = list(repo.get_workflows())
        if not workflows:
            return "📋 No workflows found."
        
        result = ["⚡ GitHub Actions Workflows:"]
        result.append("-" * 35)
        
        for wf in workflows:
            result.append(f"  • {wf.name} (ID: {wf.id})")
            result.append(f"    Path: {wf.path}")
            result.append(f"    State: {wf.state}")
            result.append("")
        
        result.append(f"Total: {len(workflows)} workflows")
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error listing workflows: {str(e)}"

# @mcp.tool()
# async def github_trigger_workflow(owner: str, repo_name: str, workflow_id_or_name: str, ref: Optional[str] = "main") -> str:
#     """
#     Trigger a GitHub Actions workflow.
#     Args:
#         owner: Repository owner.
#         repo_name: Repository name.
#         workflow_id_or_name: Workflow ID or filename.
#         ref: Branch or tag to run workflow on (default: main).
#     Returns:
#         Status of workflow trigger.
#     """
#     missing_params = []
#     if not owner: missing_params.append("owner")
#     if not repo_name: missing_params.append("repo_name")
#     if not workflow_id_or_name: missing_params.append("workflow_id_or_name")
    
#     if missing_params:
#         return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
#     try:
#         repo = get_repo_instance(owner, repo_name)
#         workflow = repo.get_workflow(workflow_id_or_name)
#         workflow.create_dispatch(ref=ref)
#         return f"✅ Workflow '{workflow.name}' triggered successfully on ref '{ref}'."
#     except Exception as e:
#         return f"❌ Error triggering workflow: {str(e)}"




# async def github_clone_repository(
#     url: Optional[str] = None,
#     owner: str = DEFAULT_OWNER,
#     repo_name: str = None,
#     local_path: Optional[str] = None,
#     branch: str = "main"
# ) -> str:
#     """
#     Clone a GitHub repository to local machine.
#     Accepts either a full URL or an owner + repo name.
#     """
#     try:
#         if url:
#             # Extract repo_name if not provided
#             if not repo_name:
#                 repo_name = url.split("/")[-1].replace(".git", "")
#         else:
#             if not repo_name or not owner:
#                 return ":x: Missing required parameters: either 'url' OR ('owner' and 'repo_name')"
#             url = f"https://{GITHUB_TOKEN}@github.com/{owner}/{repo_name}.git"
#         if not local_path:
#             local_path = get_local_repo_path(repo_name)
#         # Remove existing directory if it exists
#         if os.path.exists(local_path):
#             shutil.rmtree(local_path)
#         # Clone
#         git.Repo.clone_from(url, local_path, branch=branch)
#         return f":white_tick: Repository cloned successfully to '{local_path}' on branch '{branch}'"
#     except Exception as e:
#         return f":x: Error cloning repository: {str(e)}"


# @mcp.tool()
# async def github_clone_repository(
#     url: Optional[str] = None,
#     owner: str = DEFAULT_OWNER,
#     repo_name: str = None,
#     local_path: Optional[str] = None,
#     branch: str = "main"
# ) -> str:
#     """
#     Clone a GitHub repository to local machine.
#     Accepts either a full URL or an owner + repo name.
#     """

#     return github_clone_repository(url, owner, repo_name, local_path, branch)











@mcp.tool()
async def github_clone_repository(
    url: Optional[str] = None,
    owner: str = DEFAULT_OWNER,
    repo_name: str = None,
    local_path: Optional[str] = None,
    branch: str = "main"
) -> str:
    """
    Clone a GitHub repository to local machine.
    Accepts either a full URL or an owner + repo name.
    """
    try:
        if url:
            # Extract repo_name if not provided
            if not repo_name:
                repo_name = url.split("/")[-1].replace(".git", "")
        else:
            if not repo_name or not owner:
                return ":x: Missing required parameters: either 'url' OR ('owner' and 'repo_name')"
            url = f"https://{GITHUB_TOKEN}@github.com/{owner}/{repo_name}.git"
        if not local_path:
            local_path = get_local_repo_path(repo_name)
        # Remove existing directory if it exists
        if os.path.exists(local_path):
            shutil.rmtree(local_path)
        # Clone
        git.Repo.clone_from(url, local_path, branch=branch)
        return f":white_tick: Repository cloned successfully to '{local_path}' on branch '{branch}'"
    except Exception as e:
        return f":x: Error cloning repository: {str(e)}"

@mcp.tool()
async def github_checkout_branch(repo_name: str, branch_name: str, create_new: Optional[bool] = False) -> str:
    """
    Checkout to a specific branch in local repository.
    Args:
        repo_name: Repository name (for local path determination).
        branch_name: Branch name to checkout.
        create_new: Whether to create a new branch (default: False).
    Returns:
        Status of branch checkout.
    """
    missing_params = []
    if not repo_name: missing_params.append("repo_name")
    if not branch_name: missing_params.append("branch_name")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    local_path = get_local_repo_path(repo_name)
    
    if not os.path.exists(local_path):
        return f"❌ Repository not found locally at '{local_path}'. Please clone first using 'clone_repository'."
    
    try:
        local_repo = git.Repo(local_path)
        
        if create_new:
            # Create and checkout new branch
            new_branch = local_repo.create_head(branch_name)
            new_branch.checkout()
            return f"✅ Created and checked out new branch '{branch_name}'"
        else:
            # Checkout existing branch
            if branch_name in [head.name for head in local_repo.heads]:
                # Local branch exists
                local_repo.git.checkout(branch_name)
            else:
                # Try to checkout remote branch
                local_repo.git.checkout('-b', branch_name, f'origin/{branch_name}')
            return f"✅ Checked out branch '{branch_name}'"
    
    except Exception as e:
        return f"❌ Error checking out branch: {str(e)}"

@mcp.tool()
async def github_commit_changes(repo_name: str, message: str, files_to_add: Optional[str] = None) -> str:
    """
    commit changes in local repository.
    Args:
        repo_name: Repository name (for local path determination).
        message: Commit message.
        files_to_add: Comma-separated list of files to add (optional, adds all if not specified).
    Returns:
        Status of commit operation.
    """
    missing_params = []
    if not repo_name: missing_params.append("repo_name")
    if not message: missing_params.append("message")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    local_path = get_local_repo_path(repo_name)
    
    if not os.path.exists(local_path):
        return f"❌ Repository not found locally at '{local_path}'. Please clone first using 'clone_repository'."
    
    try:
        local_repo = git.Repo(local_path)
        
        if files_to_add:
            # Add specific files
            files_list = [f.strip() for f in files_to_add.split(',')]
            for file_path in files_list:
                local_repo.index.add([file_path])
        else:
            # Add all changes
            local_repo.git.add('--all')
        
        # Check if there are changes to commit
        if local_repo.index.diff("HEAD"):
            local_repo.index.commit(message)
            return f"✅ Changes committed successfully with message: '{message}'"
        else:
            return "ℹ️ No changes to commit"
    
    except Exception as e:
        return f"❌ Error committing changes: {str(e)}"

@mcp.tool()
async def github_push_changes(repo_name: str, branch: Optional[str] = None, remote: Optional[str] = "origin") -> str:
    """
    Push changes to remote repository.
    Args:
        repo_name: Repository name (for local path determination).
        branch: Branch to push (optional, pushes current branch if not specified).
        remote: Remote name (default: origin).
    Returns:
        Status of push operation.
    """
    if not repo_name:
        return "❌ Missing required parameter: repo_name"
    
    local_path = get_local_repo_path(repo_name)
    
    if not os.path.exists(local_path):
        return f"❌ Repository not found locally at '{local_path}'. Please clone first using 'clone_repository'."
    
    try:
        local_repo = git.Repo(local_path)
        
        if branch is None:
            # Push current branch
            current_branch = local_repo.active_branch.name
            local_repo.git.push(remote, current_branch)
            return f"✅ Pushed changes successfully to '{remote}/{current_branch}'"
        else:
            # Push specific branch
            local_repo.git.push(remote, branch)
            return f"✅ Pushed changes successfully to '{remote}/{branch}'"
    
    except Exception as e:
        return f"❌ Error pushing changes: {str(e)}"

@mcp.tool()
async def github_get_repo_status(repo_name: str) -> str:
    """
    Get current repository status.
    Args:
        repo_name: Repository name (for local path determination).
    Returns:
        Current repository status information.
    """
    if not repo_name:
        return "❌ Missing required parameter: repo_name"
    
    local_path = get_local_repo_path(repo_name)
    
    if not os.path.exists(local_path):
        return f"❌ Repository not found locally at '{local_path}'. Please clone first using 'clone_repository'."
    
    try:
        local_repo = git.Repo(local_path)
        
        # Get current branch
        current_branch = local_repo.active_branch.name
        
        # Get modified files
        modified_files = [item.a_path for item in local_repo.index.diff(None)]
        
        # Get untracked files
        untracked_files = local_repo.untracked_files
        
        # Get staged files
        staged_files = [item.a_path for item in local_repo.index.diff("HEAD")]
        
        result = [
            "📊 Repository Status:",
            "=" * 25,
            f"Current Branch: {current_branch}",
            f"Modified Files: {', '.join(modified_files) if modified_files else 'None'}",
            f"Untracked Files: {', '.join(untracked_files) if untracked_files else 'None'}",
            f"Staged Files: {', '.join(staged_files) if staged_files else 'None'}"
        ]
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ Error getting repository status: {str(e)}"

@mcp.tool()
async def github_create_local_file(repo_name: str, file_path: str, content: str) -> str:
    """
    Create a file locally in the repository.
    Args:
        repo_name: Repository name (for local path determination).
        file_path: Path where to create the file.
        content: File content.
    Returns:
        Status of file creation.
    """
    missing_params = []
    if not repo_name: missing_params.append("repo_name")
    if not file_path: missing_params.append("file_path")
    if not content: missing_params.append("content")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    local_path = get_local_repo_path(repo_name)
    
    if not os.path.exists(local_path):
        return f"❌ Repository not found locally at '{local_path}'. Please clone first using 'clone_repository'."
    
    try:
        full_path = os.path.join(local_path, file_path)
        
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w') as f:
            f.write(content)
        
        return f"✅ File '{file_path}' created successfully locally"
        
    except Exception as e:
        return f"❌ Error creating file: {str(e)}"

@mcp.tool()
async def github_pull_changes(repo_name: str, branch: Optional[str] = None) -> str:
    """
    Pull latest changes from remote repository.
    Args:
        repo_name: Repository name (for local path determination).
        branch: Branch to pull from (optional, pulls current branch if not specified).
    Returns:
        Status of pull operation.
    """
    if not repo_name:
        return "❌ Missing required parameter: repo_name"
    
    local_path = get_local_repo_path(repo_name)
    
    if not os.path.exists(local_path):
        return f"❌ Repository not found locally at '{local_path}'. Please clone first using 'clone_repository'."
    
    try:
        local_repo = git.Repo(local_path)
        
        if branch:
            local_repo.git.pull('origin', branch)
            return f"✅ Pulled latest changes successfully from origin/{branch}"
        else:
            local_repo.git.pull()
            return "✅ Pulled latest changes successfully from current branch"
        
    except Exception as e:
        return f"❌ Error pulling changes: {str(e)}"

@mcp.tool()
async def github_open_file_in_vscode(file_path: str) -> str:
    """
    Open a specified file in Visual Studio Code.
    Args:
        file_path: Path to the file to open.
    Returns:
        Status of the operation.
    """
    if not file_path:
        return "❌ Missing required parameter: file_path"
    
    try:
        # Use subprocess to open the file in VSCode
        subprocess.run(["code", file_path], check=True)
        return f"✅ Successfully opened '{file_path}' in Visual Studio Code."
    except subprocess.CalledProcessError as e:
        return f"❌ Error opening file in VSCode: {str(e)}"
    except FileNotFoundError:
        return "❌ VSCode is not installed or not found in the system PATH."
    except Exception as e:
        return f"❌ An unexpected error occurred: {str(e)}"

@mcp.tool()
async def github_create_repository(repo_name: str, description: Optional[str] = "", private: Optional[bool] = False, auto_init: Optional[bool] = True) -> str:
    """
    Create a new repository in the authenticated user's account.
    Args:
        repo_name: Name for the new repository.
        description: Repository description (optional).
        private: Make repository private (default: False).
        auto_init: Initialize with README (default: True).
    Returns:
        Status and details of repository creation.
    """
    if not repo_name:
        return "❌ Missing required parameter: repo_name"
    
    try:
        user = g.get_user()
        new_repo = user.create_repo(
            repo_name,
            description=description,
            private=private,
            auto_init=auto_init
        )
        
        result = [
            "✅ Repository created successfully!",
            f"Name: {repo_name}",
            f"Owner: {user.login}",
            f"URL: {new_repo.html_url}",
            f"Private: {'Yes' if private else 'No'}"
        ]
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error creating repository: {str(e)}"

@mcp.tool()
async def github_delete_repository(owner: str, repo_name: str) -> str:
    """
    Delete a repository (requires admin permissions).
    Args:
        owner: Repository owner.
        repo_name: Repository name.
    Returns:
        Status of repository deletion.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        target_repository = g.get_repo(f"{owner}/{repo_name}")
        target_repository.delete()
        return f"✅ Repository '{owner}/{repo_name}' deleted successfully"
    except Exception as e:
        return f"❌ Error deleting repository: {str(e)}"

@mcp.tool()
async def github_list_user_repositories() -> str:
    """
    List all repositories for the authenticated user.
    Returns:
        List of user's repositories.
    """
    try:
        user = g.get_user()
        repos = list(user.get_repos())
        
        if not repos:
            return "📋 No repositories found for your account."
        
        result = [f"📋 Your Repositories ({user.login}):"]
        result.append("-" * 40)
        
        for repo_item in repos:
            visibility = "Private" if repo_item.private else "Public"
            result.append(f"• {repo_item.full_name} ({visibility})")
            if repo_item.description:
                result.append(f"  Description: {repo_item.description}")
            result.append(f"  URL: {repo_item.html_url}")
            result.append("")
        
        result.append(f"Total: {len(repos)} repositories")
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error listing repositories: {str(e)}"

@mcp.tool()
async def github_list_organization_repositories(org_name: str) -> str:
    """
    List repositories in an organization.
    Args:
        org_name: Organization name.
    Returns:
        List of organization repositories.
    """
    if not org_name:
        return "❌ Missing required parameter: org_name"
    
    try:
        org = g.get_organization(org_name)
        repos = list(org.get_repos())
        
        if not repos:
            return f"📋 No repositories found in organization '{org_name}'."
        
        result = [f"📋 Repositories in {org_name}:"]
        result.append("-" * 40)
        
        for repo_item in repos:
            visibility = "Private" if repo_item.private else "Public"
            result.append(f"• {repo_item.full_name} ({visibility})")
            if repo_item.description:
                result.append(f"  Description: {repo_item.description}")
            result.append(f"  URL: {repo_item.html_url}")
            result.append("")
        
        result.append(f"Total: {len(repos)} repositories")
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error listing organization repositories: {str(e)}"

@mcp.tool()
async def github_get_github_user_info(username: Optional[str] = None) -> str:
    """
    Get GitHub user information.
    Args:
        username: GitHub username (optional, gets current user if not specified).
    Returns:
        User information.
    """
    try:
        if username:
            user = g.get_user(username)
        else:
            user = g.get_user()
        
        result = [
            f"👤 GitHub User Information:",
            "=" * 30,
            f"Username: {user.login}",
            f"Name: {user.name or 'Not specified'}",
            f"Email: {user.email or 'Not public'}",
            f"Bio: {user.bio or 'Not specified'}",
            f"Company: {user.company or 'Not specified'}",
            f"Location: {user.location or 'Not specified'}",
            f"Public Repos: {user.public_repos}",
            f"Followers: {user.followers}",
            f"Following: {user.following}",
            f"Profile URL: {user.html_url}"
        ]
        
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error getting user information: {str(e)}"

@mcp.tool()
async def github_get_repository_info(owner: str, repo_name: str) -> str:
    """
    Get detailed information about a repository.
    Args:
        owner: Repository owner.
        repo_name: Repository name.
    Returns:
        Repository information.
    """
    missing_params = []
    if not owner: missing_params.append("owner")
    if not repo_name: missing_params.append("repo_name")
    
    if missing_params:
        return f"❌ Missing required parameters: {', '.join(missing_params)}"
    
    try:
        repo = get_repo_instance(owner, repo_name)
        result = [
            f"📊 Repository Information:",
            "=" * 30,
            f"Name: {repo.name}",
            f"Full Name: {repo.full_name}",
            f"Description: {repo.description or 'No description'}",
            f"URL: {repo.html_url}",
            f"Clone URL: {repo.clone_url}",
            f"Private: {'Yes' if repo.private else 'No'}",
            f"Default Branch: {repo.default_branch}",
            f"Stars: {repo.stargazers_count}",
            f"Forks: {repo.forks_count}",
            f"Watchers: {repo.watchers_count}",
            f"Open Issues: {repo.open_issues_count}",
            f"Language: {repo.language or 'Not specified'}",
            f"Size: {repo.size} KB",
            f"Created: {repo.created_at}",
            f"Updated: {repo.updated_at}"
        ]
        
        return "\n".join(result)
    except Exception as e:
        return f"❌ Error getting repository information: {str(e)}"


### Tool Registry Setup ###
from typing import List, Dict, Any
from langchain.tools import BaseTool
from langchain_core.tools import tool as langchain_tool

# List all tools for easy registration
all_tools = [
    github_github_greeter,
    github_list_branches,
    github_create_branch,
    github_delete_branch,
    github_create_file,
    github_update_file,
    github_delete_file,
    github_list_pull_requests,
    github_create_pull_request,
    github_merge_pull_request,
    github_close_pull_request,
    github_list_issues,
    github_create_issue,
    github_close_issue,
    github_comment_on_issue,
    github_list_collaborators,
    github_add_collaborator,
    github_list_workflows,
    github_clone_repository,
    github_checkout_branch,
    github_commit_changes,
    github_push_changes,
    github_get_repo_status,
    github_create_local_file,
    github_pull_changes,
    github_open_file_in_vscode,
    github_create_repository,
    github_delete_repository,
    github_list_user_repositories,
    github_list_organization_repositories,
    github_get_github_user_info,
    github_get_repository_info
    ]

def get_tool_registry() -> Dict[str, BaseTool]:
    """Convert all tools to LangChain tools for registration"""
    tool_registry = {}
    
    for tool_func in all_tools:
        # Convert function to LangChain tool
        tool = langchain_tool(tool_func)
        # Use the function name as the key
        tool_registry[tool_func.__name__] = tool
    
    return tool_registry

# Add this to run both MCP server and tool registry when main is executed
if __name__ == "__main__":
    # Initialize tool registry
    tool_registry = get_tool_registry()
    print(f"🔧 Registered {len(tool_registry)} GitHub tools for chaining")
    print("📋 All tools are now independent - no global repository state required")
    
    # Run MCP server
    mcp.run()
    
# python3 /Users/thrisham/Desktop/cobol_code/github_actions/MCP_3/g_server.py