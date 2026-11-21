# Estoque Simples — Sistema de Controle de Estoque

Aplicação web acadêmica para cadastro de produtos e fornecedores, registro de entradas e saídas e consulta do saldo e do histórico de movimentações.

## Tecnologias
- Python 3.10 ou superior
- Flask
- SQLite (banco relacional embarcado)
- HTML5 e CSS
- pytest para testes automatizados

## Funcionalidades
- Painel com contadores e aviso de produtos no estoque mínimo.
- CRUD de produtos (o sistema bloqueia a exclusão de produtos com movimentações relacionadas).
- CRUD de fornecedores (bloqueia a exclusão de fornecedor associado a produto).
- Registro de entradas e saídas.
- Bloqueio de saída superior ao saldo disponível.
- Consulta de movimentações com filtros por produto e tipo.
- Saldo calculado a partir do livro de movimentações, para manter a rastreabilidade.

## Executar localmente

### Windows (PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Abra `http://127.0.0.1:5000` no navegador. O banco `instance/estoque.db` e as tabelas são criados automaticamente na primeira requisição.

Para uso fora de um ambiente acadêmico/local, configure uma chave secreta própria na variável de ambiente `SECRET_KEY`, desligue o modo debug e acrescente autenticação, proteção CSRF, controles de acesso, backups e monitoramento.

## Testes
```bash
python -m pytest -q
```

## Estrutura
```text
app.py                         # rotas, validações e regras de negócio
schema.sql                     # estrutura do banco relacional
templates/                     # páginas HTML Jinja
static/style.css               # estilos responsivos
tests/                         # testes automatizados
docs/                          # fontes dos diagramas
```

## Modelo de dados
- `suppliers`: fornecedores.
- `products`: dados de cadastro dos produtos e estoque mínimo.
- `stock_movements`: entradas e saídas; o saldo atual é calculado pela soma das quantidades de entrada menos as de saída.

A exclusão de lançamentos de movimentação não é disponibilizada pela interface, pois o histórico deve ser preservado. Correções de estoque devem ser registradas como movimentação compensatória e justificadas no campo de observação.

## Repositório GitHub
1. Crie um repositório chamado `projeto-controle-estoque`.
2. Extraia os arquivos deste pacote e copie o conteúdo da pasta para o repositório local.
3. Execute `git init`, `git add .`, `git commit -m "Implementa sistema de controle de estoque"` e `git branch -M main`.
4. Conecte o repositório remoto criado no GitHub e execute `git push -u origin main`.
5. Se o repositório for privado, adicione o tutor e `fernandonakagawa-unifil` como colaboradores com a permissão solicitada pela disciplina.

## Limitações conhecidas
Esta versão é voltada a demonstração acadêmica local. Não implementa autenticação de usuários, controle de permissões, importação de planilhas, integração fiscal, leitura por código de barras ou deploy em servidor público.

## Documentação acadêmica
O diretório `docs/` contém:
- `Documentacao_Estoque_Simples.pdf`: versão para leitura e entrega (16 páginas).
- `Documentacao_Estoque_Simples.docx`: versão editável.
- `documentacao_projeto.md`: fonte em Markdown.
- `diagramas/`: arquivos `.dot` e imagens dos diagramas de caso de uso, DER, atividade, classes e cinco diagramas de sequência.

Antes de enviar o PDF ao tutor, substitua os campos entre colchetes na capa e personalize a conclusão para descrever o que você aprendeu. Confira também o sumário depois das alterações.
