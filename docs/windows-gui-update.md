# Windows GUI update

- The launch screen uses a horizontal hexagon and wordmark, with direct access to
  modelling and an eleven-step guided tour. Home returns here without clearing work.
- LEC-UFPR, Labirinto and OpenDrift logos link to the supplied official websites.
  The OpenDrift paper is cited; Fonseca et al. is marked as a forthcoming manuscript
  pending final publication details.
- Search suggestions have an opaque white surface and a teal selection highlight.
- Finish setup checks every setup decision and opens Review & run; an incomplete
  decision is shown with feedback instead.
- Numerical fields omit trailing zeros while retaining their existing precision
  and locale-specific decimal separator.
- Study area shows either environmental coverage and buffer or manual coordinates,
  depending on the selected source. The existing map remains below those controls.
- Validation has a central teal animated progress panel, removed when checks finish,
  fail or become stale after an edit.

## Verification

Run the GUI tests with `python -m unittest discover -s tests -p '*gui*.py'`.
Use `python tools/render_windows_polish.py` for wide and compact Qt screenshots.
For a packaged GUI-only check, use `Marine Drift Workbench.exe --gui-check <folder>`;
it writes a JSON report and welcome screenshot without starting a simulation.

The laboratory images were supplied by the user and are bundled under
`src/marine_drift_desktop/ui/assets/partners` without modifying the source artwork.
