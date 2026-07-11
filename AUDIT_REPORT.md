# GhostScripter knowledge and functionality audit

Audit date: 2026-07-10  
Games checked: English Steam K1 and K2/TSL, clean retail archives plus installed saves  
Scope: public-format knowledge used by GhostScripter, every registered MCP tool,
core readers/writers, editor data sources, project persistence, packaging inputs,
and automated tests.

## What “public knowledge” means here

There is no finite index of every KotOR forum post or private modding discovery.
This audit covered the active public sources GhostScripter cites or overlaps:

- [PyKotor and Holocron Toolset](https://github.com/OldRepublicDevs/PyKotor)
- [xoreos and xoreos-tools](https://github.com/xoreos/xoreos)
- [Reone](https://github.com/seedhartha/reone)
- [KotOR.js](https://github.com/th3w1zard1/KotOR.js)
- [KobaltBlu’s scripting-tool headers](https://github.com/KobaltBlu/KotOR-Scripting-Tool)
- [KotOR Modding Wiki](https://kotor-modding.fandom.com/wiki/KotOR_Modding_Wiki)
- [Deadly Stream tutorials and research](https://deadlystream.com/forum/10-modding-and-editing/)
- [LucasForums archive](https://lucasforumsarchive.com/)
- [TSLPatcher’s official readme](https://github-wiki-see.page/m/NickHugi/PyKotor/wiki/TSLPatcher%27s-Official-Readme)

Public claims were treated as leads, not truth. A claim was promoted to high
confidence only when it agreed with retail data or at least two independent
implementations. Generated wiki pages and NWN-only references were not used as
KotOR authorities without a game-specific cross-check.

## Highest-risk findings and disposition

| Area | Audit finding | Disposition |
|---|---|---|
| Game archives | Module MOD/ERF/RIM resources and texture ERFs were not indexed, so real DLG/UTC/TPC assets appeared absent. | Fixed with precedence-aware archive indexing and module-context lookup. |
| DLG | END (`-1`) links became node `0`; typed node deletion could delete the opposite list; K2 root/link/StuntList fields were dropped. | Fixed. Imported binary fidelity is retained through UI and MCP JSON; unsafe imported writes are refused. |
| GFF | `writeGFF` guessed types and falsely claimed to invert `readGFF`; retail `global.jrl` was severely altered. | Replaced with a typed lossless JSON schema. Untyped writes require explicit `allowLossy=true`. |
| NWScript compiler | PyKotor 2.3.12 omitted K2 action 876 and 45 constants and lost a real `PlayPazaak` parameter. | The compiler is supplied the pinned bundled declaration tables: 772 K1 and 877 K2 actions. |
| NWScript reference | Parser omitted `sLanguage`, split vector defaults, exposed duplicate K2 constants inconsistently, and the editor contained NWN:EE-only types/fake fallback signatures. | Fixed; declarations and duplicate provenance are explicit; hand-written fallback data was removed. |
| NCS reconstruction | A decompiler could return an almost-empty script while the tool called it source. | Disassembly is always returned. Reconstructed source is verified by exact recompilation or labelled non-authoritative. |
| SSF | Writer used an invented/shifted slot list and emitted short 28-entry files, discarding meaningful retail tail entries. | One canonical 28-name table is shared; readers preserve all trailing entries; new files use the retail-standard 40 entries. |
| LIP | Index 0 was correctly neutral, but most remaining labels and the phoneme map were stale. | Replaced with Reone’s experimentally revised mapping and retail-validated neutral pose; old non-ambiguous aliases remain accepted. |
| Module names | A 68-entry table claimed PyKotor provenance, but 29 of 34 retail-overlapping entries were wrong. | Deleted. Names come from the installed ARE LocString and that game’s TLK; unknown remains unknown. |
| Saves | `readSave` used wrong field names/locations and returned hardcoded empty party/global data. | Rebuilt on typed SaveInfo, PartyTable, GlobalVars, and nested SAVEGAME.sav resources with component completeness reporting. |
| UTC composite | Equipment was read from invented top-level fields and several script hooks had wrong labels. | Routed through PyKotor’s typed UTC model and real Equip_ItemList struct IDs/script hooks. |
| 2DA patches | Export called a pseudo format “TSLPatcher changes.ini”; inline edits/columns were not fully undoable. | Emits real `[2DAList]` operation sections, refuses unrepresentable deletion/reorder, and records undo state. |
| Projects/quests | Project manifests persisted metadata only; generated “scripts” were names, often over 16 characters. | Artifacts now persist/discover from disk; quest JSON is lossless; real compileable `.nss` files use deterministic legal ResRefs. |
| Resource types | Unknown extensions silently became type 0; type 2045’s `.dft`/`.dtf` alias was mishandled. | Both documented aliases are accepted and unknown archive types are rejected. |
| Release build | The CI builder omitted the bundled NWScript database and dynamically loaded GFF/SSF/LIP/services/MCP code; its second build also deleted the folder artifact. | Runtime data and audited dynamic modules are explicitly bundled, and the second build preserves earlier artifacts. |
| Legacy compiler EXEs | Two bundled binaries are byte-identical but have no established source revision/build provenance. | Quarantined: not packaged or auto-executed. PyKotor is primary; only a user-installed PATH compiler is a fallback. |

## Retail-backed evidence

- K1 `dialog.tlk`: 49,265 entries / 5,394,446 bytes, exact-byte round-trip.
- K2 `dialog.tlk`: 136,329 entries / 10,162,930 bytes, exact-byte round-trip.
- K1 and K2 `global.jrl`: exact-byte typed GFF round-trips (77,301 and
  87,040 bytes respectively).
- Representative K1/K2 2DAs round-tripped byte-identically and parsed with
  PyKotor.
- K1 indexed 234 RIMs and resolved `bastila.dlg` from `danm13_s.rim`; K2
  resolved `101kreia.dlg` from `101PER_dlg.erf`.
- Every installed SSF decoded: K1 106 files (98×172 bytes, 8×208 bytes), K2
  70 files (all 172 bytes). Non-empty undocumented index 33 values were retained.
- LIP corpus: all 12,910 non-empty unique K1 files and all 14,851 K2 files end
  at neutral shape 0; K2 also begins at 0 in every file.
- Real K1 and K2 autosaves yielded party/global data and nested module snapshots;
  genuine zero and false values stayed zero/false.
- Real K1 Bastila and K2 Kreia UTCs produced typed equipment, classes, powers,
  skills, feats, and actual Script* hooks.

## Automated verification

- Full suite: 1,513 passed, 65 skipped, and 309 subtests passed.
- Retail-install integration suite: 41 passed against the installed English
  Steam copies of K1 and K2/TSL.
- The Windows folder release was rebuilt, launched offscreen for eight seconds,
  and remained alive without an initialization failure.
- The release contains both pinned NWScript declaration sets and their provenance
  manifest, plus the audited GFF, SSF, LIP, services, GUI, and MCP modules. It
  does not contain the quarantined legacy compiler executables.
- All Python modules compile, the focused release-integrity tests pass, and
  `git diff --check` reports no whitespace errors.

## Source conflicts resolved

### LIP semantics

The older [KotOR Modding Wiki LIP table](https://kotor-modding.fandom.com/wiki/LIP_Format)
and older editor derivatives label index 0 as `EE`. Retail frame behavior proves
that it is the neutral/rest pose. The remaining semantic groups use
[Reone’s revised experimental mapping](https://github.com/seedhartha/reone/commit/fef1401ca2a8),
including its [phoneme composer](https://github.com/seedhartha/reone/blob/master/src/libs/tools/lip/composer.cpp).
Only 0=neutral is conclusive retail evidence; labels 1–15 remain high-quality
reverse engineering rather than an official BioWare legend.

### SSF size versus known names

[PyKotor’s enum](https://github.com/OldRepublicDevs/PyKotor/blob/master/Libraries/PyKotor/src/pykotor/resource/formats/ssf/ssf_data.py)
names 28 semantic slots, but retail files are longer. Independent readers in
[Reone](https://github.com/seedhartha/reone/blob/master/src/libs/resource/format/ssfreader.cpp)
and [xoreos](https://github.com/xoreos/xoreos/blob/master/src/aurora/ssffile.cpp)
derive the entry count from file length. GhostScripter therefore distinguishes
“28 known names” from “all stored entries” and preserves the latter.

### K2 NWScript declarations

The pinned K2 header has 877 ordered actions, corroborated by
[xoreos](https://github.com/xoreos/xoreos/blob/master/src/engines/kotor2/script/function_tables.h)
and [KotOR.js](https://github.com/th3w1zard1/KotOR.js/blob/master/src/nwscript/NWScriptDefK2.ts).
It is a community-corrected header, not a literal retail dump; its provenance
and hashes are in `resources/scripts/manifest.json`.

### TSLPatcher output

The exporter now follows the documented `[2DAList]`, file section, and named
operation-section grammar in the
[TSLPatcher 2DA syntax guide](https://github-wiki-see.page/m/NickHugi/PyKotor/wiki/TSLPatcher-2DAList-Syntax).
Operations that syntax cannot express safely, such as deleting a row, produce
an error instead of a plausible-looking fake patch.

## Remaining limitations

- NCS source reconstruction cannot be guaranteed. The instruction listing is
  authoritative; source is explicitly status-labelled.
- Reone’s LIP labels 1–15 are the strongest current experimental mapping, not
  official documentation.
- Interactive GUI coverage remains much lower than core-format coverage. The
  automated suite exercises models/services/widgets, but a signed release still
  needs a human smoke pass on Windows and at least one clean Linux build.
- The legacy nwnnsscomp binaries remain in repository history pending a
  reproducible provenance decision; runtime code never auto-executes them.
- This audit does not certify every historical forum post. It records the
  public corpus and reproducible retail checks used for GhostScripter’s actual
  behavior.

## Integrity rules added by this audit

1. Unknown data is returned as unknown or rejected—never filled with a guessed label/value.
2. Generic binary writes must retain field types or be explicitly marked lossy.
3. Imported fidelity-sensitive assets carry their source schema through JSON/UI boundaries.
4. Public knowledge embedded in the release has a pinned source, hash, confidence, and known deviations.
5. A structurally valid file is not considered correct until semantic retail fixtures also pass.
