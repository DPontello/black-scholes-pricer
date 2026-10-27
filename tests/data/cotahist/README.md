# Fixture sintética do COTAHIST e do Cadastro de Instrumentos

**Os dados desta pasta são inventados.** Nenhum arquivo real da B3 é
redistribuído aqui (ROADMAP, Sprint 5): os preços, tickers e o cadastro foram
gerados por `build_fixture.py` para exercitar o `CotahistOptionChainAdapter`
e o painel de renda.

Para regenerar, da raiz do repositório:

```bash
PYTHONPATH=src python -m tests.data.cotahist.build_fixture
```

O gerador é determinístico: os fechamentos saem de retornos senoidais fixos e
os prêmios das opções saem do próprio kernel sob um smile conhecido,
arredondados ao centavo. O teste `test_fixture_versionada_e_a_que_o_gerador_produz`
falha se os arquivos versionados divergirem do que o gerador produz. Os
arquivos são tratados como binários pelo git (`.gitattributes`), para que os
bytes, inclusive o fim de linha `\r\n`, sejam os mesmos em qualquer sistema.

Conteúdo e casos de borda: docstring de `build_fixture.py`.
