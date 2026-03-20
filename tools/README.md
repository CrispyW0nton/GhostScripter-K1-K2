# tools/

This directory holds **optional third-party executables** that GhostScripter
can use to extend its functionality.

## nwnnsscomp — KotOR NWScript Compiler

The script editor can compile `.nss` → `.ncs` using the official NWN/KotOR
compiler binary.

| Platform | Filename |
|----------|---------|
| Windows  | `nwnnsscomp.exe` |
| Linux    | `nwnnsscomp` |
| macOS    | `nwnnsscomp` |

**How to get it:**
- Download from [nwntools/nwnnsscomp](https://github.com/nwntools/nwnnsscomp/releases)
  or extract from any NWN2 / KOTOR toolkit.
- Place the binary in **this directory** (`tools/`).
- The build script (`build_tools/build.py`) will automatically bundle it into
  the EXE if it is present.

Without the compiler, GhostScripter falls back to a built-in Python syntax
checker that highlights common errors without producing a `.ncs` file.

---

> Place `nwnnsscomp.exe` (or `nwnnsscomp` on Linux/macOS) here and then
> rebuild, or drop it next to `GhostScripter-K1-K2.exe` in the distributed
> folder.
