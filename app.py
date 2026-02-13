#!/usr/bin/env python3

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="OpenClaw Dashboard", version="2.0.0")

# Constants
OPENCLAW_BIN = "/home/adityonugrohoid/.nvm/versions/node/v22.22.0/bin/openclaw"
OPENCLAW_CONFIG = "/home/adityonugrohoid/.openclaw/openclaw.json"
WORKSPACE_PATH = "/home/adityonugrohoid/.openclaw/workspace"
SKILLS_PATH = "/home/adityonugrohoid/.nvm/versions/node/v22.22.0/lib/node_modules/openclaw/skills"

# Favicon
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico", media_type="image/x-icon")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

def run_command(cmd: str, timeout: int = 15) -> Dict[str, Any]:
    """Run shell command with timeout and proper PATH"""
    try:
        env = os.environ.copy()
        env["PATH"] = "/home/adityonugrohoid/.nvm/versions/node/v22.22.0/bin:" + env.get("PATH", "")
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        return {
            "success": True,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command timed out",
            "timeout": timeout
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def redact_sensitive_value(key: str, value: Any) -> Any:
    """Redact sensitive values (tokens, keys, secrets)"""
    if isinstance(value, str):
        sensitive_keywords = ['token', 'key', 'secret', 'password', 'auth', 'api']
        if any(keyword in key.lower() for keyword in sensitive_keywords):
            if len(value) > 8:
                return f"{value[:4]}...{value[-4:]}"
            else:
                return "***"
    return value

def redact_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact sensitive values in config"""
    if isinstance(config, dict):
        return {k: redact_config(redact_sensitive_value(k, v)) for k, v in config.items()}
    elif isinstance(config, list):
        return [redact_config(item) for item in config]
    else:
        return config

def get_file_size_mb(path: Path) -> float:
    """Get file size in MB"""
    try:
        return path.stat().st_size / 1024 / 1024
    except:
        return 0.0

def get_directory_size(path: Path) -> int:
    """Get total size of directory in bytes"""
    total = 0
    try:
        for item in path.rglob('*'):
            if item.is_file():
                total += item.stat().st_size
    except:
        pass
    return total

def format_size(size_bytes: int) -> str:
    """Format size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def build_file_tree(path: Path, max_depth: int = 4, current_depth: int = 0) -> Dict[str, Any]:
    """Build file tree structure"""
    if current_depth >= max_depth:
        return {"name": path.name, "type": "truncated"}
    
    try:
        if path.is_file():
            return {
                "name": path.name,
                "type": "file",
                "size": path.stat().st_size,
                "size_str": format_size(path.stat().st_size),
                "modified": int(path.stat().st_mtime)
            }
        elif path.is_dir():
            children = []
            try:
                for item in sorted(path.iterdir()):
                    if not item.name.startswith('.'):  # Skip hidden files
                        children.append(build_file_tree(item, max_depth, current_depth + 1))
            except PermissionError:
                pass
            
            return {
                "name": path.name,
                "type": "directory",
                "children": children,
                "size": get_directory_size(path),
                "size_str": format_size(get_directory_size(path))
            }
    except:
        return {"name": path.name, "type": "error"}

def parse_markdown_frontmatter(content: str) -> Dict[str, str]:
    """Parse YAML frontmatter from markdown"""
    lines = content.split('\n')
    if not lines or lines[0] != '---':
        return {}
    
    frontmatter_lines = []
    for i, line in enumerate(lines[1:], 1):
        if line == '---':
            break
        frontmatter_lines.append(line)
    
    # Simple YAML parsing for title/description
    result = {}
    for line in frontmatter_lines:
        if ':' in line:
            key, value = line.split(':', 1)
            result[key.strip()] = value.strip().strip('"\'')
    
    return result

@app.get("/")
async def serve_index():
    """Serve the main dashboard HTML"""
    return FileResponse("static/index.html")

@app.get("/api/config")
async def get_config():
    """Get OpenClaw configuration with redacted sensitive values"""
    try:
        with open(OPENCLAW_CONFIG, 'r') as f:
            config = json.load(f)
        
        redacted_config = redact_config(config)
        
        # Organize by sections
        sections = {
            "auth": redacted_config.get("auth", {}),
            "agents": redacted_config.get("agents", {}),
            "session": redacted_config.get("session", {}),
            "channels": redacted_config.get("channels", {}),
            "gateway": redacted_config.get("gateway", {}),
            "hooks": redacted_config.get("hooks", {}),
            "skills": redacted_config.get("skills", {}),
            "plugins": redacted_config.get("plugins", {})
        }
        
        return {
            "success": True,
            "sections": sections,
            "raw": redacted_config
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="OpenClaw config not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def parse_ascii_table(text: str, table_name: str) -> List[Dict[str, str]]:
    """Parse ASCII table format with │ separators"""
    lines = text.split('\n')
    
    # Find table start
    table_start = -1
    for i, line in enumerate(lines):
        if table_name.lower() in line.lower() and ('┌' in lines[i+1] if i+1 < len(lines) else False):
            table_start = i
            break
    
    if table_start == -1:
        return []
    
    # Extract headers and data rows
    headers = []
    data_rows = []
    
    for i in range(table_start + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            break
        
        # Skip separator lines (├, ┌, └)
        if '├' in line or '┌' in line or '└' in line:
            continue
            
        # Parse table row
        if '│' in line:
            cells = [cell.strip() for cell in line.split('│')[1:-1]]  # Remove first and last empty parts
            if not headers and cells:
                headers = cells
            elif cells and len(cells) == len(headers):
                data_rows.append(dict(zip(headers, cells)))
    
    return data_rows

@app.get("/api/session")
async def get_session():
    """Get OpenClaw session status"""
    cmd_result = run_command(f"{OPENCLAW_BIN} status")
    
    if not cmd_result["success"]:
        raise HTTPException(status_code=500, detail=cmd_result.get("error", "Failed to get session status"))
    
    raw_output = cmd_result["stdout"]
    
    # Parse Overview table
    overview_data = parse_ascii_table(raw_output, "Overview")
    overview = {}
    for row in overview_data:
        if "Item" in row and "Value" in row:
            overview[row["Item"].lower().replace(" ", "_")] = row["Value"]
    
    # Parse Sessions table
    sessions_data = parse_ascii_table(raw_output, "Sessions")
    sessions = []
    for row in sessions_data:
        if "Key" in row:
            sessions.append({
                "key": row.get("Key", ""),
                "kind": row.get("Kind", ""),
                "age": row.get("Age", ""),
                "model": row.get("Model", ""),
                "tokens": row.get("Tokens", "")
            })
    
    # Parse Channels table
    channels_data = parse_ascii_table(raw_output, "Channels")
    channels_status = []
    for row in channels_data:
        if "Channel" in row:
            channels_status.append({
                "channel": row.get("Channel", ""),
                "enabled": row.get("Enabled", ""),
                "state": row.get("State", ""),
                "detail": row.get("Detail", "")
            })
    
    # Extract Security summary
    security_summary = ""
    for line in raw_output.split('\n'):
        if "Summary:" in line and ("critical" in line or "warn" in line or "info" in line):
            security_summary = line.strip()
            break
    
    # Read config file for additional info
    config_info = {}
    try:
        with open(OPENCLAW_CONFIG, 'r') as f:
            config = json.load(f)
        
        # Extract key config values
        defaults = config.get("agents", {}).get("defaults", {})
        session_config = config.get("session", {})
        
        model_raw = defaults.get("model", {})
        model_name = model_raw.get("primary", "unknown") if isinstance(model_raw, dict) else str(model_raw)
        
        compaction_raw = defaults.get("compaction", {})
        compaction_mode = compaction_raw.get("mode", "unknown") if isinstance(compaction_raw, dict) else str(compaction_raw)
        
        thinking_level = defaults.get("thinkingDefault", "unknown")
        reasoning_on = thinking_level not in ("off", "unknown", "none", "")
        
        config_info = {
            "model": model_name,
            "thinking": thinking_level,
            "reasoning": "On" if reasoning_on else "Off",
            "dm_scope": session_config.get("dmScope", "unknown"),
            "compaction": compaction_mode
        }
    except Exception as e:
        print(f"Failed to read config: {e}")
    
    return {
        "success": True,
        "raw": raw_output,
        "overview": overview,
        "config_info": config_info,
        "sessions": sessions,
        "channels_status": channels_status,
        "security_summary": security_summary
    }

@app.get("/api/memory")
async def get_memory():
    """Get workspace memory files"""
    workspace = Path(WORKSPACE_PATH)
    memory_dir = workspace / "memory"
    
    # Core workspace files
    core_files = ["MEMORY.md", "SOUL.md", "USER.md", "IDENTITY.md", "AGENTS.md", "TOOLS.md", "HEARTBEAT.md"]
    workspace_files = []
    
    for filename in core_files:
        file_path = workspace / filename
        if file_path.exists():
            try:
                content = file_path.read_text(encoding='utf-8')
                workspace_files.append({
                    "name": filename,
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                    "size_str": format_size(file_path.stat().st_size),
                    "modified": int(file_path.stat().st_mtime),
                    "content": content
                })
            except Exception as e:
                workspace_files.append({
                    "name": filename,
                    "path": str(file_path),
                    "error": str(e)
                })
    
    # Daily log files from memory directory
    daily_logs = []
    if memory_dir.exists():
        try:
            for log_file in sorted(memory_dir.glob("*.md"), reverse=True):
                try:
                    content = log_file.read_text(encoding='utf-8')
                    truncated = len(content) > 2000
                    daily_logs.append({
                        "name": log_file.name,
                        "path": str(log_file),
                        "size": log_file.stat().st_size,
                        "size_str": format_size(log_file.stat().st_size),
                        "modified": int(log_file.stat().st_mtime),
                        "content": content[:2000] + "..." if truncated else content,
                        "truncated": truncated
                    })
                except Exception as e:
                    daily_logs.append({
                        "name": log_file.name,
                        "error": str(e)
                    })
        except Exception:
            pass
    
    # Calculate totals
    total_files = len(workspace_files) + len(daily_logs)
    total_size = sum(f.get("size", 0) for f in workspace_files + daily_logs)
    
    return {
        "success": True,
        "workspace_files": workspace_files,
        "daily_logs": daily_logs,
        "totals": {
            "total_files": total_files,
            "total_size": total_size,
            "total_size_str": format_size(total_size),
            "daily_logs_count": len(daily_logs)
        }
    }

@app.get("/api/skills")
async def get_skills():
    """Get installed OpenClaw skills"""
    skills_path = Path(SKILLS_PATH)
    
    if not skills_path.exists():
        return {
            "success": False,
            "error": "Skills directory not found"
        }
    
    skills = []
    try:
        for skill_dir in skills_path.iterdir():
            if skill_dir.is_dir() and not skill_dir.name.startswith('.'):
                skill_md = skill_dir / "SKILL.md"
                
                skill_info = {
                    "name": skill_dir.name,
                    "path": str(skill_dir),
                    "file_count": len(list(skill_dir.rglob("*"))) if skill_dir.exists() else 0
                }
                
                if skill_md.exists():
                    try:
                        content = skill_md.read_text(encoding='utf-8')
                        frontmatter = parse_markdown_frontmatter(content)
                        skill_info["title"] = frontmatter.get("title", skill_dir.name)
                        skill_info["description"] = frontmatter.get("description", "")
                    except Exception as e:
                        skill_info["error"] = str(e)
                
                skills.append(skill_info)
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
    
    return {
        "success": True,
        "skills": sorted(skills, key=lambda x: x["name"]),
        "count": len(skills)
    }

@app.get("/api/workspace")
async def get_workspace():
    """Get workspace file tree structure"""
    workspace = Path(WORKSPACE_PATH)
    
    if not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace directory not found")
    
    # Build file tree
    tree = build_file_tree(workspace, max_depth=4)
    
    # Count files and directories
    def count_items(node):
        if node["type"] == "file":
            return {"files": 1, "dirs": 0}
        elif node["type"] == "directory":
            files = dirs = 0
            dirs += 1  # Count this directory
            for child in node.get("children", []):
                counts = count_items(child)
                files += counts["files"]
                dirs += counts["dirs"]
            return {"files": files, "dirs": dirs}
        return {"files": 0, "dirs": 0}
    
    counts = count_items(tree)
    total_size = get_directory_size(workspace)
    
    return {
        "success": True,
        "tree": tree,
        "totals": {
            "files": counts["files"],
            "directories": counts["dirs"],
            "total_size": total_size,
            "total_size_str": format_size(total_size)
        }
    }

@app.get("/api/channels")
async def get_channels():
    """Get channel configuration"""
    try:
        with open(OPENCLAW_CONFIG, 'r') as f:
            config = json.load(f)
        
        channels = config.get("channels", {})
        session = config.get("session", {})
        
        # Add session dmScope to channel info
        for channel_name, channel_config in channels.items():
            if isinstance(channel_config, dict):
                channel_config["dmScope"] = session.get("dmScope", "")
        
        return {
            "success": True,
            "channels": channels,
            "dm_scope": session.get("dmScope", "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/security")
async def get_security():
    """Get security audit results"""
    cmd_result = run_command(f"{OPENCLAW_BIN} security audit")
    
    if not cmd_result["success"]:
        return {
            "success": False,
            "error": cmd_result.get("error", "Failed to run security audit"),
            "raw": cmd_result.get("stderr", "")
        }
    
    raw_output = cmd_result["stdout"]
    
    # Parse summary counts
    critical_count = warn_count = info_count = 0
    
    for line in raw_output.split('\n'):
        if "Summary:" in line:
            # Extract counts from "Summary: X critical · Y warn · Z info"
            import re
            critical_match = re.search(r'(\d+)\s+critical', line)
            warn_match = re.search(r'(\d+)\s+warn', line)
            info_match = re.search(r'(\d+)\s+info', line)
            
            if critical_match:
                critical_count = int(critical_match.group(1))
            if warn_match:
                warn_count = int(warn_match.group(1))
            if info_match:
                info_count = int(info_match.group(1))
            break
    
    # Parse findings
    findings = []
    lines = raw_output.split('\n')
    current_finding = None
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Check for severity markers
        if line_stripped in ['CRITICAL', 'WARN', 'INFO']:
            # Next line should contain finding ID and title
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line:
                    # Parse finding ID and title
                    parts = next_line.split(' ', 1)
                    finding_id = parts[0] if parts else ""
                    title = parts[1] if len(parts) > 1 else next_line
                    
                    current_finding = {
                        "severity": line_stripped.lower(),
                        "id": finding_id,
                        "title": title,
                        "description": "",
                        "fix": ""
                    }
                    
                    # Collect description lines (indented lines following the finding)
                    desc_lines = []
                    fix_lines = []
                    collecting_fix = False
                    
                    for j in range(i + 2, len(lines)):
                        desc_line = lines[j]
                        if desc_line.startswith('  ') and desc_line.strip():
                            desc_content = desc_line.strip()
                            if desc_content.startswith('Fix:'):
                                collecting_fix = True
                                fix_lines.append(desc_content[4:].strip())
                            elif collecting_fix:
                                fix_lines.append(desc_content)
                            else:
                                desc_lines.append(desc_content)
                        elif desc_line.strip() in ['CRITICAL', 'WARN', 'INFO'] or not desc_line.startswith(' '):
                            break
                    
                    current_finding["description"] = '\n'.join(desc_lines)
                    current_finding["fix"] = '\n'.join(fix_lines)
                    findings.append(current_finding)
    
    return {
        "success": True,
        "raw": raw_output,
        "summary": {
            "critical": critical_count,
            "warning": warn_count,
            "info": info_count
        },
        "findings": findings
    }

@app.get("/api/system")
async def get_system():
    """Get system information"""
    try:
        # Get system information using psutil
        boot_time = psutil.boot_time()
        uptime = int(time.time() - boot_time)
        
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Format uptime
        uptime_str = f"{uptime // 86400}d {(uptime % 86400) // 3600}h {(uptime % 3600) // 60}m"
        
        return {
            "success": True,
            "hostname": os.uname().nodename,
            "os": f"{os.uname().sysname} {os.uname().release}",
            "kernel": os.uname().version,
            "uptime": uptime,
            "uptime_str": uptime_str,
            "cpu": {
                "count": psutil.cpu_count(),
                "usage": psutil.cpu_percent(interval=1)
            },
            "memory": {
                "total": memory.total,
                "used": memory.used,
                "free": memory.available,
                "percent": memory.percent,
                "total_str": format_size(memory.total),
                "used_str": format_size(memory.used),
                "free_str": format_size(memory.available)
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": (disk.used / disk.total) * 100,
                "total_str": format_size(disk.total),
                "used_str": format_size(disk.used),
                "free_str": format_size(disk.free)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def main():
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8501, reload=True)

if __name__ == "__main__":
    main()