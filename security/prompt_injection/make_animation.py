"""
Animated GIF of the prompt-injection red-team result.

Reads the saved run_*.json result files and animates the attack matrix
across the four defence conditions (none -> sandbox -> sanitise -> both),
flipping each attack cell fired->blocked and counting the ASR down.

Output: results/asr_animation.gif

Requires: matplotlib, imageio, pillow  (pip install matplotlib imageio pillow)
Usage:    python security/prompt_injection/make_animation.py
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
import imageio.v2 as imageio
from PIL import Image

HERE    = Path(__file__).resolve().parent
RESULTS = HERE / "results"
FRAMES  = RESULTS / "_frames"

# Defence conditions in order, with display labels and result files.
CONDS = [
    ("No defence", "run_poisoned_none.json"),
    ("Sandbox",    "run_poisoned_sandbox.json"),
    ("Sanitise",   "run_poisoned_sanitise.json"),
    ("Both",       "run_poisoned_both.json"),
]

# Short display kind per attack id (family, label).
DISPLAY = {
    "direct_override":         ("Direct",        "Blunt imperative"),
    "direct_polite":           ("Direct",        "Polite phrasing"),
    "fake_system":             ("Impersonation", "Fake SYSTEM message"),
    "context_boundary":        ("Impersonation", "Context-boundary spoof"),
    "delimiter_injection":     ("Impersonation", "Fake numbered passage"),
    "authority_framing":       ("Social",        "Authority framing"),
    "instruction_in_citation": ("Social",        "Instruction-as-citation"),
    "payload_split":           ("Obfuscation",   "Split payload"),
    "exfiltration_full":       ("Exfiltration",  "Full prompt disclosure"),
    "exfiltration_firstline":  ("Exfiltration",  "First-line disclosure"),
}

# --- palette (dark, GitHub-style) -------------------------------------
BG="#0d1117"; PANEL="#161b22"; INK="#e6edf3"; SUB="#8b949e"
RED="#e24b4a"; RED_BG="#3a1414"; RED_BR="#a32d2d"
GRN="#3fb950"; GRN_BG="#0f2e1a"; GRN_BR="#238636"; ACCENT="#58a6ff"

COLS=2; CELL_W=4.6; CELL_H=1.02; GAP_X=0.35; GAP_Y=0.26; X0=0.4
MATRIX_TOP=4.55


def load():
    """Return ordered attack ids, and {cond_label: set(fired_ids)}."""
    order, fired = None, {}
    for label, fname in CONDS:
        data = json.loads((RESULTS / fname).read_text())
        rows = data["rows"]
        if order is None:
            order = [r["id"] for r in rows]
        fired[label] = {r["id"] for r in rows if r["injection_fired"]}
    return order, fired


def lerp(a,b,t): return a+(b-a)*t
def hex2rgb(h):
    h=h.lstrip("#"); return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))
def mix(c1,c2,t):
    a,b=hex2rgb(c1),hex2rgb(c2); return tuple(lerp(a[i],b[i],t) for i in range(3))


def draw_frame(order, fired, cond_idx, morph, count_val, fname):
    labels = [c[0] for c in CONDS]
    cond = labels[cond_idx]; prev = labels[max(cond_idx-1,0)]

    fig,ax=plt.subplots(figsize=(11,7.8),dpi=100)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0,11); ax.set_ylim(0,7.8); ax.axis("off")

    ax.text(0.4,7.42,"Indirect prompt-injection red-team",
            color=INK,fontsize=20,fontweight="bold",va="center")
    ax.text(0.4,6.98,"10 attack variants   |   Llama 3.2 3B   |   local RAG (splaim-local-rag)",
            color=SUB,fontsize=11.5,va="center")

    asr_pct=count_val/len(order)*100
    ax.text(10.6,7.42,f"{asr_pct:.0f}%",color=ACCENT if asr_pct>0 else GRN,
            fontsize=34,fontweight="bold",va="center",ha="right")
    ax.text(10.6,6.9,f"{count_val:.0f} of {len(order)} fired",color=SUB,
            fontsize=11.5,va="center",ha="right")

    pill_y=6.15; pill_h=0.5; pill_w=2.35; n=len(labels)
    total_w=10.2; slot=total_w/n
    for i,c in enumerate(labels):
        on=(i==cond_idx); cx=0.4+slot*i+(slot-pill_w)/2
        ax.add_patch(FancyBboxPatch((cx,pill_y),pill_w,pill_h,
                boxstyle="round,pad=0.02,rounding_size=0.1",linewidth=1.4,
                edgecolor=ACCENT if on else "#30363d",
                facecolor=PANEL if on else BG,zorder=2))
        ax.text(cx+pill_w/2,pill_y+pill_h/2,c,color=INK if on else SUB,
                fontsize=11.5,fontweight="bold" if on else "normal",
                va="center",ha="center",zorder=3)
        if on:
            ax.plot([cx+0.2,cx+pill_w-0.2],[pill_y-0.06,pill_y-0.06],
                    color=ACCENT,lw=2.4,zorder=3)

    for k,aid in enumerate(order):
        fam,kind=DISPLAY.get(aid,("",aid))
        r=k//COLS; c=k%COLS
        x=X0+c*(CELL_W+GAP_X); y=MATRIX_TOP-r*(CELL_H+GAP_Y)
        was=aid in fired[prev]; now=aid in fired[cond]
        t=morph if was!=now else (1.0 if now else 0.0)
        if was and not now:
            face=mix(RED_BG,GRN_BG,t); brd=mix(RED_BR,GRN_BR,t); dot=mix(RED,GRN,t)
        else:
            if now: face,brd,dot=hex2rgb(RED_BG),hex2rgb(RED_BR),hex2rgb(RED)
            else:   face,brd,dot=hex2rgb(GRN_BG),hex2rgb(GRN_BR),hex2rgb(GRN)
        lw=1.5+(1.6*np.sin(np.pi*t) if (was and not now) else 0)
        ax.add_patch(FancyBboxPatch((x,y),CELL_W,CELL_H,
                boxstyle="round,pad=0.02,rounding_size=0.07",
                linewidth=lw,edgecolor=brd,facecolor=face,zorder=2))
        label_col=mix(RED,GRN,t) if (was and not now) else (RED if now else GRN)
        ax.text(x+0.28,y+CELL_H-0.28,fam,color=label_col,fontsize=8.5,va="center",zorder=3)
        ax.text(x+0.28,y+0.36,kind,color=INK,fontsize=11.5,fontweight="bold",va="center",zorder=3)
        cur_fired=now if t>=0.5 else was
        ax.scatter([x+CELL_W-1.05],[y+0.4],s=40,color=dot,zorder=3)
        ax.text(x+CELL_W-0.9,y+0.4,"fired" if cur_fired else "blocked",
                color=dot,fontsize=9.5,va="center",zorder=3)

    ax.scatter([0.55],[0.2],s=44,color=RED)
    ax.text(0.72,0.2,"injection fired",color=SUB,fontsize=10,va="center")
    ax.scatter([2.55],[0.2],s=44,color=GRN)
    ax.text(2.72,0.2,"blocked",color=SUB,fontsize=10,va="center")
    ax.text(10.6,0.2,"github.com/Nivedita-Saha/splaim-local-rag",
            color="#484f58",fontsize=9,va="center",ha="right")

    fig.savefig(fname,facecolor=BG,bbox_inches="tight",pad_inches=0.15)
    plt.close(fig)


def main():
    order, fired = load()
    labels = [c[0] for c in CONDS]
    counts = {lab: len(fired[lab]) for lab in labels}

    FRAMES.mkdir(exist_ok=True)
    for old in FRAMES.glob("*.png"):
        old.unlink()

    files=[]; fi=0; FLIP=14; HOLD=16
    def add(ci,morph,count):
        nonlocal fi
        f=FRAMES/f"f{fi:03d}.png"
        draw_frame(order,fired,ci,morph,count,f)
        files.append(f); fi+=1

    for _ in range(HOLD): add(0,1.0,counts[labels[0]])
    for ci in range(1,len(labels)):
        cp=counts[labels[ci-1]]; cn=counts[labels[ci]]
        for s in range(1,FLIP+1):
            t=s/FLIP; te=0.5-0.5*np.cos(np.pi*t); add(ci,te,lerp(cp,cn,te))
        for _ in range(HOLD): add(ci,1.0,cn)

    sizes=[Image.open(f).size for f in files]
    w=min(s[0] for s in sizes); h=min(s[1] for s in sizes)
    norm=[np.array(Image.open(f).convert("RGB").resize((w,h))) for f in files]

    out=RESULTS/"asr_animation.gif"
    imageio.mimsave(out,norm,duration=0.07,loop=0)
    for f in files: f.unlink()
    FRAMES.rmdir()
    print(f"Rendered {len(files)} frames -> {out} ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
