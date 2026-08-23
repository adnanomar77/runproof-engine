# RunProof real execution report

## Input

The execution used the real project file `README.md` from this repository. No synthetic dataset was created.

## Workflow

1. Register the file as an input with `copy_inputs=True`.
2. Read the file using Python's UTF-8 file reader.
3. Count characters, lines, words, and Markdown headings.
4. Assert that the file contains at least one line.
5. Save `profile.json` inside the RunProof artifact.

## Result

- Status: `verified`
- Run ID: `20260823T171612Z-e36ac482be`
- Characters: `3427`
- Lines: `73`
- Words: `446`
- Markdown headings: `8`
- Steps: `2`
- Checks: `1`
- Outputs: `1`
- Artifact: `demo-runs/real_file_profile/20260823T171612Z-e36ac482be`

## Independent verification

The CLI installed from the public PyPI package verified the generated artifact with status `verified`, no reasons, and mode `integrity`.

## Engineering note

The first local run exposed a relative-path bug when a relative root was used. The source tree was corrected to resolve the run root absolutely, and the corrected source run succeeded. The already published `0.1.0` package predates that source fix for creating new runs; a patch release should be published before claiming the PyPI package contains this correction.
