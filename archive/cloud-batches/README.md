# Archived cloud batches

These files are the earlier cloud-queue, pilot, and upload-package records. They are not current entry points.

`PACKAGE_MANIFEST.json` is the manifest of the original upload package, kept as it was packed. The queue and pilot scripts expect that package's root layout, including `run_batch_v31.sh`, a prepared `.runtime/vision_python`, and the cloud paths named in the notes. They are not wired to `data/examples_manifest.json`.

Use the repository root for the current commands: `setup.sh`, `download_models.sh`, `run_test.sh`, `run_all.sh`, and `export_results.sh`.
