"""
GhostScripter-K1-K2 — Web Preview Server
Serves a static demo of the application interface.
"""
import os
import sys
import base64
from pathlib import Path

from flask import Flask, send_from_directory, render_template_string

app = Flask(__name__)
BASE = Path(__file__).parent


def img_b64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GhostScripter-K1-K2 — KotOR Modding IDE</title>
<style>
  :root {
    --bg: #1e1e1e;
    --panel: #252526;
    --panel-hdr: #2d2d30;
    --border: #3c3c3c;
    --text: #d4d4d4;
    --text-dim: #858585;
    --accent: #0078d4;
    --accent-hover: #1a8fe0;
    --selection: #094771;
    --error: #f48771;
    --success: #4ec9b0;
    --warning: #dcdcaa;
    --keyword: #569cd6;
    --func: #dcdcaa;
    --comment: #57a64a;
    --string: #ce9178;
    --number: #b5cea8;
    --type: #4ec9b0;
    --constant: #9cdcfe;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', Arial, sans-serif;
         font-size: 13px; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }

  /* Title Bar */
  .titlebar {
    background: #111111;
    height: 30px;
    display: flex;
    align-items: center;
    padding: 0 12px;
    gap: 8px;
    flex-shrink: 0;
    border-bottom: 1px solid #000;
    user-select: none;
  }
  .titlebar-logo { color: var(--accent); font-weight: bold; font-size: 12px; }
  .titlebar-title { color: var(--text-dim); font-size: 11px; }
  .titlebar-controls { margin-left: auto; display: flex; gap: 6px; }
  .titlebar-btn {
    width: 12px; height: 12px; border-radius: 50%; border: none; cursor: pointer;
  }
  .tb-close { background: #ff5f57; }
  .tb-min { background: #febc2e; }
  .tb-max { background: #28c840; }

  /* Menu Bar */
  .menubar {
    background: var(--panel);
    height: 26px;
    display: flex;
    align-items: center;
    padding: 0 4px;
    gap: 2px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border);
  }
  .menu-item {
    padding: 3px 10px;
    border-radius: 3px;
    cursor: pointer;
    color: #cccccc;
    font-size: 12px;
  }
  .menu-item:hover { background: #3c3c3c; }

  /* Toolbar */
  .toolbar {
    background: var(--panel);
    height: 34px;
    display: flex;
    align-items: center;
    padding: 0 6px;
    gap: 4px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border);
  }
  .tb-btn {
    height: 24px;
    padding: 0 10px;
    border-radius: 3px;
    border: 1px solid #555;
    background: #3c3c3c;
    color: #cccccc;
    cursor: pointer;
    font-size: 11px;
    white-space: nowrap;
  }
  .tb-btn:hover { background: #4a4a4a; color: white; }
  .tb-btn.primary {
    background: var(--accent);
    border-color: var(--accent-hover);
    color: white;
    font-weight: bold;
  }
  .tb-btn.primary:hover { background: var(--accent-hover); }
  .tb-sep { width: 1px; height: 20px; background: var(--border); margin: 0 4px; }

  /* Main layout */
  .main-layout {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  /* Left panel */
  .left-panel {
    width: 220px;
    background: var(--panel);
    border-right: 2px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    overflow: hidden;
  }
  .panel-header {
    background: var(--panel-hdr);
    color: #cccccc;
    font-weight: bold;
    font-size: 12px;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .game-selector-row {
    background: var(--panel-hdr);
    padding: 3px 8px;
    display: flex;
    align-items: center;
    gap: 6px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .game-selector-row label { color: var(--text-dim); font-size: 11px; }
  .game-select {
    background: #3c3c3c; color: #cccccc; border: 1px solid #555;
    border-radius: 3px; padding: 2px 6px; font-size: 11px;
  }
  .tree-view { flex: 1; overflow-y: auto; padding: 4px 0; }
  .tree-item {
    padding: 3px 8px 3px 20px;
    cursor: pointer;
    font-size: 11px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .tree-item:hover { background: #2a2d2e; }
  .tree-item.selected { background: var(--selection); color: white; }
  .tree-cat {
    padding: 4px 8px;
    cursor: pointer;
    font-size: 11px;
    font-weight: bold;
    color: var(--warning);
    display: flex;
    align-items: center;
    gap: 6px;
    border-top: 1px solid #2a2a2a;
  }
  .tree-cat .arrow { color: var(--text-dim); font-size: 9px; }
  .tree-cat.quest { color: var(--keyword); }
  .tree-cat.dialogue { color: var(--type); }
  .tree-cat.model { color: var(--string); }
  .tree-cat.root { color: var(--constant); font-size: 12px; }
  .panel-btns {
    background: var(--panel);
    border-top: 1px solid var(--border);
    padding: 4px 6px;
    display: flex;
    gap: 4px;
    flex-shrink: 0;
  }
  .panel-btn {
    flex: 1;
    height: 22px;
    background: #3c3c3c;
    border: 1px solid #555;
    border-radius: 3px;
    color: #cccccc;
    cursor: pointer;
    font-size: 10px;
  }
  .panel-btn:hover { background: #4a4a4a; }

  /* Center - editor area */
  .center-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* Tab bar */
  .tab-bar {
    background: var(--panel);
    display: flex;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }
  .tab-bar::-webkit-scrollbar { height: 4px; }
  .tab-bar::-webkit-scrollbar-track { background: var(--panel); }
  .tab-bar::-webkit-scrollbar-thumb { background: #555; }
  .tab {
    padding: 6px 14px;
    border: 1px solid var(--border);
    border-bottom: none;
    background: var(--panel-hdr);
    color: #969696;
    cursor: pointer;
    white-space: nowrap;
    font-size: 11px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .tab.active {
    background: var(--bg);
    color: white;
    border-top: 2px solid var(--accent);
  }
  .tab:hover:not(.active) { background: #3c3c3c; color: #cccccc; }
  .tab-close { color: var(--text-dim); font-size: 10px; cursor: pointer; padding: 0 2px; }
  .tab-close:hover { color: white; }

  /* Editor content */
  .editor-content {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* Code Editor (script tab) */
  .code-editor-wrap {
    flex: 1;
    display: flex;
    overflow: hidden;
  }
  .line-numbers {
    background: var(--bg);
    color: var(--text-dim);
    font-family: 'Consolas', monospace;
    font-size: 12px;
    padding: 8px 6px 8px 4px;
    text-align: right;
    border-right: 1px solid var(--border);
    min-width: 40px;
    user-select: none;
    overflow: hidden;
    line-height: 1.6;
  }
  .code-area {
    flex: 1;
    background: var(--bg);
    font-family: 'Consolas', monospace;
    font-size: 12px;
    padding: 8px 12px;
    overflow: auto;
    line-height: 1.6;
  }
  .code-area pre { white-space: pre; margin: 0; }
  .kw { color: var(--keyword); font-weight: bold; }
  .fn { color: var(--func); }
  .cm { color: var(--comment); font-style: italic; }
  .st { color: var(--string); }
  .nm { color: var(--number); }
  .tp { color: var(--type); font-weight: bold; }
  .cn { color: var(--constant); }

  /* Function reference sidebar */
  .func-ref {
    width: 260px;
    background: var(--panel);
    border-left: 2px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    flex-shrink: 0;
  }
  .func-search {
    background: #3c3c3c;
    border: none;
    border-bottom: 1px solid var(--border);
    color: #cccccc;
    padding: 6px 8px;
    font-size: 11px;
    width: 100%;
  }
  .func-list { flex: 1; overflow-y: auto; }
  .func-cat { color: var(--warning); font-weight: bold; font-size: 11px; padding: 6px 8px 2px; }
  .func-item {
    padding: 3px 8px 3px 16px;
    font-size: 10px;
    font-family: 'Consolas', monospace;
    color: var(--constant);
    cursor: pointer;
  }
  .func-item:hover { background: #2a2d2e; }
  .func-detail {
    height: 60px;
    background: var(--bg);
    border-top: 1px solid var(--border);
    padding: 6px 8px;
    font-size: 10px;
    color: var(--text-dim);
    overflow: hidden;
  }

  /* Output console */
  .output-panel {
    height: 130px;
    background: var(--bg);
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }
  .output-hdr {
    background: var(--panel-hdr);
    padding: 3px 8px;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .output-hdr span { color: #cccccc; font-weight: bold; font-size: 11px; }
  .output-clear {
    margin-left: auto;
    background: #3c3c3c;
    border: none;
    color: var(--text-dim);
    border-radius: 2px;
    padding: 1px 6px;
    cursor: pointer;
    font-size: 10px;
  }
  .output-content {
    flex: 1;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    padding: 6px 10px;
    overflow-y: auto;
    line-height: 1.5;
    color: var(--text);
  }
  .log-ok { color: var(--type); }
  .log-err { color: var(--error); }
  .log-warn { color: var(--warning); }
  .log-info { color: var(--text-dim); }
  .log-arrow { color: var(--keyword); }

  /* Right panel */
  .right-panel {
    width: 260px;
    background: var(--panel);
    border-left: 2px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    overflow: hidden;
  }
  .props-tabs {
    display: flex;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
  }
  .props-tab {
    padding: 5px 12px;
    font-size: 11px;
    cursor: pointer;
    color: #969696;
    border-bottom: 2px solid transparent;
  }
  .props-tab.active { color: white; border-bottom-color: var(--accent); }
  .props-content { flex: 1; overflow-y: auto; padding: 8px; }
  .props-row { display: flex; justify-content: space-between; padding: 3px 0;
               border-bottom: 1px solid #2a2a2a; }
  .props-key { color: var(--text-dim); font-size: 11px; }
  .props-val { color: var(--text); font-size: 11px; font-family: 'Consolas', monospace; }
  .props-section { color: var(--type); font-weight: bold; font-size: 11px;
                   padding: 8px 0 4px; border-bottom: 1px solid var(--border); margin-top: 4px; }

  /* Status bar */
  .statusbar {
    background: var(--accent);
    height: 22px;
    display: flex;
    align-items: center;
    padding: 0 8px;
    gap: 12px;
    flex-shrink: 0;
  }
  .statusbar span { color: white; font-size: 11px; }
  .statusbar .sep { opacity: 0.4; }

  /* Scrollbars */
  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: #424242; border-radius: 2px; }
  ::-webkit-scrollbar-thumb:hover { background: #686868; }

  /* Screenshot image */
  .screenshot-banner {
    position: absolute;
    top: 0;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0,0,0,0.8);
    color: white;
    padding: 6px 16px;
    border-radius: 0 0 6px 6px;
    font-size: 11px;
    z-index: 100;
  }
</style>
</head>
<body>

<!-- Title Bar -->
<div class="titlebar">
  <div class="titlebar-logo">GhostScripter-K1-K2</div>
  <div class="titlebar-title">KotOR 1 &amp; 2 TSL Modding IDE  ·  v1.0.0</div>
  <div class="titlebar-controls">
    <div class="titlebar-btn tb-min"></div>
    <div class="titlebar-btn tb-max"></div>
    <div class="titlebar-btn tb-close"></div>
  </div>
</div>

<!-- Menu Bar -->
<div class="menubar">
  <div class="menu-item">File</div>
  <div class="menu-item">Edit</div>
  <div class="menu-item">View</div>
  <div class="menu-item">Project</div>
  <div class="menu-item">Tools</div>
  <div class="menu-item">Help</div>
</div>

<!-- Toolbar -->
<div class="toolbar">
  <button class="tb-btn">+ Project</button>
  <button class="tb-btn">Open</button>
  <button class="tb-btn">Save</button>
  <div class="tb-sep"></div>
  <button class="tb-btn">Script Editor</button>
  <button class="tb-btn">Dialogue Editor</button>
  <button class="tb-btn primary">Quest Builder</button>
  <button class="tb-btn">2DA Manager</button>
  <button class="tb-btn">Asset Library</button>
  <div class="tb-sep"></div>
  <button class="tb-btn">Export Override</button>
  <button class="tb-btn">Export ERF</button>
</div>

<!-- Main Layout -->
<div class="main-layout">

  <!-- Left Panel: Project Tree -->
  <div class="left-panel">
    <div class="panel-header">Project</div>
    <div class="game-selector-row">
      <label>Game:</label>
      <select class="game-select">
        <option>K1</option>
        <option>K2</option>
      </select>
    </div>
    <div class="tree-view">
      <div class="tree-cat root">▼ &nbsp;MyAwesomeMod</div>
      <div class="tree-cat">▼ Scripts (3)</div>
      <div class="tree-item selected">k_swg_demo_start.nss</div>
      <div class="tree-item">k_swg_demo_00.nss</div>
      <div class="tree-item">k_swg_demo_01.nss</div>
      <div class="tree-cat quest">▼ Quests (1)</div>
      <div class="tree-item">DemoQuest</div>
      <div class="tree-cat dialogue">▼ Dialogues (1)</div>
      <div class="tree-item">k_demo_dialogue.dlg</div>
      <div class="tree-cat model">▼ Models (0)</div>
    </div>
    <div class="panel-btns">
      <button class="panel-btn">+ Project</button>
      <button class="panel-btn">Open</button>
    </div>
  </div>

  <!-- Center: Editor area -->
  <div class="center-area">

    <!-- Tab bar -->
    <div class="tab-bar">
      <div class="tab">Welcome</div>
      <div class="tab active">✎ k_swg_demo_start.nss <span class="tab-close">×</span></div>
      <div class="tab">⚔ DemoQuest <span class="tab-close">×</span></div>
      <div class="tab">🗨 k_demo_dialogue.dlg <span class="tab-close">×</span></div>
      <div class="tab">2DA Manager <span class="tab-close">×</span></div>
    </div>

    <!-- Code editor -->
    <div class="editor-content">
      <div class="code-editor-wrap">

        <!-- Script Editor toolbar mini -->
        <div style="position:relative; display:flex; flex-direction:column; flex:1; overflow:hidden;">
          <div style="background:#2d2d30; padding:3px 6px; display:flex; gap:4px; align-items:center;
                      border-bottom:1px solid #3c3c3c; flex-shrink:0;">
            <button class="tb-btn" style="height:22px; font-size:10px;">Open</button>
            <button class="tb-btn" style="height:22px; font-size:10px;">Save</button>
            <div class="tb-sep"></div>
            <button class="tb-btn primary" style="height:22px; font-size:10px;">⚙ Compile → NCS</button>
            <button class="tb-btn" style="height:22px; font-size:10px;">Decompile NCS</button>
            <div class="tb-sep"></div>
            <span style="color:#969696; font-size:10px;">Template:</span>
            <select style="background:#3c3c3c; color:#cccccc; border:1px solid #555;
                           border-radius:3px; padding:2px 6px; font-size:10px; height:22px;">
              <option>void main()</option>
              <option>StartingConditional()</option>
            </select>
            <div style="flex:1"></div>
            <span style="color:#569cd6; font-size:10px;">k_swg_demo_start</span>
          </div>

          <!-- Code + func ref -->
          <div style="display:flex; flex:1; overflow:hidden;">
            <!-- Line numbers + code -->
            <div style="display:flex; flex:1; overflow:hidden;">
              <div class="line-numbers">
1<br>2<br>3<br>4<br>5<br>6<br>7<br>8<br>9<br>10<br>11<br>12<br>
13<br>14<br>15<br>16<br>17<br>18<br>19<br>20<br>21<br>22<br>23<br>24<br>
25<br>26<br>27<br>28<br>29<br>30<br>31<br>32<br>33<br>34<br>
              </div>
              <div class="code-area">
<pre><span class="cm">// Quest Start Script — GhostScripter-K1-K2</span>
<span class="cm">// Sets quest to active state</span>

<span class="tp">void</span> <span class="fn">main</span>() {
    <span class="cm">// Activate the demo quest</span>
    <span class="fn">SetGlobalBoolean</span>(<span class="st">"K_SWG_DEMO"</span>, <span class="cn">TRUE</span>);
    <span class="fn">SetGlobalNumber</span>(<span class="st">"K_SWG_DEMO_STATE"</span>, <span class="nm">1</span>);

    <span class="cm">// Get the PC</span>
    <span class="tp">object</span> oPC = <span class="fn">GetFirstPC</span>();

    <span class="cm">// Check alignment</span>
    <span class="tp">int</span> nAlign = <span class="fn">GetGoodEvilValue</span>(oPC);
    <span class="kw">if</span> (nAlign &gt; <span class="nm">75</span>) {
        <span class="cm">// Light side bonus</span>
        <span class="fn">AdjustAlignment</span>(oPC, <span class="cn">ALIGNMENT_LIGHT_SIDE</span>, <span class="nm">5</span>, <span class="cn">FALSE</span>);
    }

    <span class="cm">// Spawn quest NPC</span>
    <span class="tp">object</span> oNPC = <span class="fn">GetObjectByTag</span>(<span class="st">"k_npc_questgiver"</span>, <span class="nm">0</span>);
    <span class="kw">if</span> (<span class="fn">GetIsObjectValid</span>(oNPC)) {
        <span class="fn">ActionStartConversation</span>(oNPC, <span class="st">"k_demo_dialogue"</span>, <span class="cn">FALSE</span>);
    }
}</pre>
              </div>
            </div>

            <!-- Function Reference -->
            <div class="func-ref">
              <div class="panel-header">Function Reference</div>
              <input class="func-search" placeholder="Search functions…" value="">
              <div class="func-list">
                <div class="func-cat">Quest / Global Variables</div>
                <div class="func-item">SetGlobalNumber(string, int)</div>
                <div class="func-item">GetGlobalNumber(string)</div>
                <div class="func-item">SetGlobalBoolean(string, int)</div>
                <div class="func-item">GetGlobalBoolean(string)</div>
                <div class="func-item">SetGlobalString(string, string)</div>
                <div class="func-cat">Object / NPC</div>
                <div class="func-item">GetObjectByTag(string, int)</div>
                <div class="func-item">CreateObject(int, string, location)</div>
                <div class="func-item">DestroyObject(object, float)</div>
                <div class="func-item">GetIsObjectValid(object)</div>
                <div class="func-cat">Conversation</div>
                <div class="func-item">BeginConversation(string, object)</div>
                <div class="func-item">ActionStartConversation(object, string)</div>
                <div class="func-cat">Party</div>
                <div class="func-item">AddPartyMember(int, object)</div>
                <div class="func-item">RemovePartyMember(int)</div>
                <div class="func-cat">Alignment</div>
                <div class="func-item">GetGoodEvilValue(object)</div>
                <div class="func-item">AdjustAlignment(object, int, int)</div>
              </div>
              <div class="func-detail">
                <span style="color:var(--func); font-weight:bold;">GetGoodEvilValue</span>
                → <span style="color:var(--type);">int</span><br>
                <span style="color:var(--text-dim);">Get Light/Dark side points (0-100) for creature.</span>
              </div>
            </div>
          </div>

          <!-- Output console -->
          <div class="output-panel">
            <div class="output-hdr">
              <span>Compiler Output</span>
              <button class="output-clear">Clear</button>
            </div>
            <div class="output-content">
              <div class="log-info">GhostScripter-K1-K2 initialized. Ready.</div>
              <div class="log-info">Version 1.0.0</div>
              <div class="log-ok">✓ Created project: MyAwesomeMod (K1)</div>
              <div class="log-info">  Location: ~/Projects/MyAwesomeMod</div>
              <div class="log-ok">✓ New script: k_swg_demo_start.nss</div>
              <div class="log-ok">✓ New quest: DemoQuest (BRANCHING_QUEST)</div>
              <div class="log-arrow">→ Compiling k_swg_demo_start.nss...</div>
              <div class="log-ok">✓ Compilation successful!</div>
            </div>
          </div>

        </div><!-- end code editor wrap -->
      </div><!-- end code editor wrap 2 -->
    </div><!-- end editor content -->

  </div><!-- end center area -->

  <!-- Right Panel: Properties -->
  <div class="right-panel">
    <div class="props-tabs">
      <div class="props-tab active">Properties</div>
      <div class="props-tab">Quick</div>
      <div class="props-tab">About</div>
    </div>
    <div class="props-content">
      <div class="props-section">Script File</div>
      <div class="props-row">
        <span class="props-key">Name</span>
        <span class="props-val" style="color:var(--warning);">k_swg_demo_start</span>
      </div>
      <div class="props-row">
        <span class="props-key">Type</span>
        <span class="props-val">quest</span>
      </div>
      <div class="props-row">
        <span class="props-key">Errors</span>
        <span class="props-val" style="color:var(--type);">0</span>
      </div>
      <div class="props-row">
        <span class="props-key">Warnings</span>
        <span class="props-val" style="color:var(--warning);">0</span>
      </div>

      <div class="props-section">Project</div>
      <div class="props-row">
        <span class="props-key">Name</span>
        <span class="props-val" style="color:var(--constant);">MyAwesomeMod</span>
      </div>
      <div class="props-row">
        <span class="props-key">Game</span>
        <span class="props-val" style="color:var(--type);">K1</span>
      </div>
      <div class="props-row">
        <span class="props-key">Version</span>
        <span class="props-val">1.0.0</span>
      </div>
      <div class="props-row">
        <span class="props-key">Scripts</span>
        <span class="props-val">3</span>
      </div>
      <div class="props-row">
        <span class="props-key">Quests</span>
        <span class="props-val">1</span>
      </div>
      <div class="props-row">
        <span class="props-key">Dialogues</span>
        <span class="props-val">1</span>
      </div>

      <div class="props-section">Quick Actions</div>
      <div style="display:flex; flex-direction:column; gap:4px; padding-top:6px;">
        <button style="background:#0078d4; color:white; border:1px solid #1a8fe0;
                        border-radius:3px; padding:5px 10px; cursor:pointer; font-weight:bold;">
          + New Quest
        </button>
        <button style="background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:5px 10px; cursor:pointer;">
          + New Script
        </button>
        <button style="background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:5px 10px; cursor:pointer;">
          + New Dialogue
        </button>
        <button style="background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:5px 10px; cursor:pointer;">
          Export Override
        </button>
        <button style="background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:5px 10px; cursor:pointer;">
          Export ERF
        </button>
      </div>
    </div>
  </div>

</div><!-- end main layout -->

<!-- Status Bar -->
<div class="statusbar">
  <span>✓ Project 'MyAwesomeMod' loaded</span>
  <span class="sep">|</span>
  <span>K1</span>
  <span class="sep">|</span>
  <span style="margin-left:auto;">GhostScripter 1.0.0</span>
</div>

</body>
</html>"""


@app.route("/")
def index():
    return HTML


@app.route("/screenshot")
def screenshot():
    if Path(BASE / "screenshot.png").exists():
        return send_from_directory(str(BASE), "screenshot.png")
    return "No screenshot available", 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
