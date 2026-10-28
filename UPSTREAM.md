# Upstream

Este repositório é um fork do **Strata** (licença MIT, ver `LICENSE`).

- Upstream: https://github.com/Niko1221/Strata
- Commit importado: `46c152a1310f77cd2f0ce2c7cd213962df14fe83` (v0.2.7, 2026-10-28 09:11 +0100)
- Método: snapshot da árvore do commit acima, sem o histórico, e sem alteração de código.
- Fora do snapshot: `.github/workflows/` (8 arquivos). O token de push não tem o escopo `workflow`, e o GitHub recusa qualquer commit (inclusive do histórico) que traga workflows. Além disso, os workflows do upstream (intake, reopen, docker-images) agiriam no fork. Os workflows do fork entram depois, no PR de CI.

Copyright (c) 2026 Niko1221 and the Strata contributors.
