# Recompiler installation metadata

Code-only installs (for example, manual shielding with button mapping disabled)
need no RomFS assets. The companion app still needs
`mods/zz-Super-Hero-Boost/.super-hero-boost` to record the bundled module variant,
SHA-256 and selected settings. The metadata is now written even when no asset
files are copied; no empty `romfs` directory is required.

## Existing installs made before this fix

Apply Settings can reconstruct a **missing** marker only after all these checks:

- The installed `subsdk9` matches the app's bundled release byte for byte after
  normalizing only fields written by `installer.patch_config`. Config headers,
  padding and all other module bytes must still match.
- Both module and image have a unique, complete version-1 config of a known
  size (72, 76 or 80 bytes).
- All three uncompressed, file-backed module segments match `image.bin` at
  their memory offsets, with only the same settings fields normalized.
- The main module has the full known game build-ID prefix, the existing
  built-install check passes, and the native executable differs in content
  from its saved original. Both current and legacy flat backups are supported.

Validation happens before backup, module, RomFS or metadata writes. Missing
payloads/images, corrupt or mismatched existing markers, unknown modules,
compressed/relocated layouts, ambiguous configs, missing executable backups,
and copies of the stock executable fail closed with the existing rebuild error.
An existing marker is never silently replaced as a recovery workaround.

This is conservative guest-module validation, not cryptographic attestation of
the native executable. The source distribution has no trusted per-build native
executable manifest. A different executable hash demonstrates a content change,
not that the right code was compiled. Unknown/custom builds may therefore need
manual investigation; never fabricate a marker to bypass a rejection.

The existing Apply Settings process-closing behavior and backup handling remain
in place. This change does not provide runtime code loading or remove the first
rebuild required to add or change gameplay code.

## Source-only regression tests

With the app's `zstandard` dependency installed:

```sh
python -m unittest discover -s tests -v
python -m compileall -q app tests
git diff --check
```

All test modules, images, executables, assets and backups are synthetic temporary
fixtures. No game dumps, release payloads, compiler, game launch or network are
needed. Real Hookshot/Longshot/ReLink build and runtime behavior must be validated
separately by a maintainer with their own local installation.
