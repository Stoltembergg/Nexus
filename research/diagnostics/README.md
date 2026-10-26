# Diagnostics de pesquisa (somente diagnóstico)

**Nunca use com uma conta real/principal. Nunca rode com o jogo conectado aos servidores oficiais.**

- `riot-mvg-dependency-trace.c` + `build-mvg-dependency-trace.py`: trace opcional via `__DATA,__interpose` que só observa (não altera) resultados de APIs chamadas pelo `mvg.framework`.
- Fica fora de `tools/`, então `scripts/configure.py` não copia para `build/runtime/tools`; nenhum instalador, launcher ou build carrega este código (garantido por `tests/test_diagnostic_isolation.py`).
- Guarda em tempo de execução: sem `NEXUS_DIAG_ALLOW_INTERPOSE=1`, o build recusa e a dylib vira pass-through puro, sem log, avisando em stderr.
