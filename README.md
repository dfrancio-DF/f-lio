# Fólio

Um visualizador de Markdown para Linux, com foco em leitura e edição opcional. Interface inspirada na clareza do Outline, usando **GTK 3 + WebKitGTK do sistema** e **GtkSourceView** para editar. Sem servidor, sem Electron, sem build de frontend e sem dependências de rede para funcionar.

## Obter o projeto

```sh
git clone https://github.com/dfrancio-DF/f-lio.git
cd f-lio
```

## Executar

```sh
./folio.sh
./folio.sh /caminho/documento.md
```

## Instalar para seu usuário

```sh
/usr/bin/python3 install.py
# Opcional: associar o duplo clique em arquivos Markdown ao Fólio
/usr/bin/python3 install.py --default
```

O instalador registra o app no menu e cria `~/.local/bin/folio`. O código continua nesta pasta; mantenha-a no lugar após instalar. Não precisa de sudo.

## Editar um documento

Os arquivos sempre abrem em **modo leitura**. Para alterar o Markdown, clique em **Editar** na barra superior ou pressione `Ctrl E`.

O editor nativo oferece realce de sintaxe, números de linha, busca e desfazer/refazer. Use **Salvar** (`Ctrl S`) para gravar, **Salvar como** (`Ctrl Shift S`) para criar uma cópia e **Leitura** (`Ctrl E`) para voltar ao documento renderizado.

- O salvamento é explícito: não há gravação automática enquanto você digita.
- Antes de sair do editor, fechar ou abrir outro arquivo, alterações pendentes podem ser salvas, descartadas ou mantidas ao cancelar a ação.
- Se outro programa alterar o arquivo durante uma edição, o Fólio preserva seu rascunho e permite recarregar o disco, salvar uma cópia ou substituir o arquivo explicitamente.
- O salvamento é atômico e preserva UTF-8, a presença de BOM, o padrão de quebras de linha (LF, CRLF ou CR) e as permissões do arquivo existente.
- A página de boas-vindas é somente leitura; abra um arquivo local para habilitar o botão **Editar**.

## Dependências do sistema

- Python 3.10+
- PyGObject, GTK 3 e WebKit2 4.1
- markdown-it-py e Pygments
- GtkSourceView 4 (`gir1.2-gtksource-4`) para o modo de edição; o leitor funciona sem essa dependência.

Em Debian/Ubuntu recentes:

```sh
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-gtksource-4 python3-markdown-it python3-pygments
```

## Recursos

- Arquivos locais por diálogo, arrastar e soltar, linha de comando ou gerenciador de arquivos.
- Leitura por padrão, com botão **Editar** para modificar o Markdown em um editor nativo.
- Índice navegável, progresso de leitura e arquivos recentes.
- Temas claro, escuro e do sistema, modo foco e ajuste do tamanho do texto.
- Busca restrita ao documento com próximo/anterior, atalhos e cópia de código.
- Código com realce de sintaxe, tabelas, listas de tarefas, imagens relativas e HTML básico sanitizado.
- Tabelas aproveitam a largura da janela, com colunas proporcionais ao conteúdo e rolagem horizontal quando necessário; parágrafos mantêm uma largura confortável de leitura.
- Atualização automática ao salvar, incluindo salvamento por substituição de arquivo.
- Links relativos para outros documentos Markdown; links web abrem no navegador padrão.
- Preferências em `$XDG_CONFIG_HOME/folio/settings.json` (padrão: `~/.config/folio/settings.json`).

Os documentos ficam no computador. Imagens com URL remota podem usar a rede. JavaScript e estilos dos documentos não são executados. Diagramas Mermaid e fórmulas LaTeX não fazem parte desta primeira versão.

## Atalhos

| Atalho | Ação |
| --- | --- |
| Ctrl O | Abrir |
| Ctrl E | Editar / voltar à leitura |
| Ctrl S | Salvar, no editor |
| Ctrl Shift S | Salvar como, no editor |
| Ctrl Z / Ctrl Shift Z (ou Ctrl Y) | Desfazer / refazer, no editor |
| Ctrl F | Buscar |
| Enter / Shift Enter, na busca | Próximo / anterior |
| Ctrl Shift F | Modo foco |
| Ctrl + / Ctrl - | Tamanho do texto |
| Ctrl 0 | Restaurar tamanho |
| Ctrl R | Recarregar |
| Esc | Fechar busca / sair do foco |

## Verificações

```sh
/usr/bin/python3 -m unittest discover -s tests -v
xvfb-run -a /usr/bin/python3 tests/native_smoke.py
xvfb-run -a /usr/bin/python3 tests/native_editing.py
xvfb-run -a -s "-screen 0 1920x1200x24" /usr/bin/python3 tests/table_layout.py
```

## Remover a integração

Remova `~/.local/bin/folio`, `~/.local/share/applications/io.github.folio.Reader.desktop` e `~/.local/share/icons/hicolor/scalable/apps/io.github.folio.Reader.svg`. A pasta do projeto e as preferências são independentes.

## Licença

Este projeto é distribuído sob a [licença MIT](LICENSE).
