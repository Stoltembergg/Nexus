# Correção experimental: popup vazio do Zorin AppIndicator

Este experimento **não** é recomendado para uso diário. Ele altera um arquivo
gerenciado por pacote de uma extensão do GNOME Shell, vale apenas para a
versão instalada e pode ser invalidado por atualizações do pacote. Nada é
aplicado automaticamente: nem à extensão, nem ao runtime, nem ao cliente.

O código-fonte da extensão (`dbusMenu.js`) é de terceiros e **não é
versionado neste repositório**. O repositório guarda apenas o diff
(`dbusMenu.patch`) e os testes, que aplicam o patch sobre uma cópia
temporária do arquivo instalado no momento da execução.

Nenhuma instalação, alteração da configuração ou reinício foi realizado. A
ponte própria e processos de aplicativos não foram alterados.

## Evidência e comportamento

No GNOME Shell 46.0 local, `/usr/lib/gnome-shell/libshell-14.so` contém
`/org/gnome/shell/ui/popupMenu.js`. `PopupMenu.open()` retorna sem emitir
abertura se `isEmpty()`, que ignora separadores e exige algum filho visível.
A extensão sincroniza `visible` do item D-Bus com o ator. Antes, qualquer
filho no root fazia ambos os sinais aguardarem abertura, mesmo com todos
ocultos. A correção adia somente quando o cache tem filho direto visível que
não seja separador; cache incompleto é tratado conservadoramente como
adiável. Os caminhos originais de sinal, flags, agrupamento e cancelamento não
foram modificados.

O teste `gjs -m test.js` compila ambas as fontes, executa os métodos reais do
cliente com dependências simuladas e reproduz o bloqueio na versão instalada.
Testa visibilidade, remoção de propriedade, layout, separador, root vazio,
cache incompleto, adiamento, ativação repetida e cancelamento de requisição
substituída. Não é teste de integração de Shell/D-Bus nem cobre destruição
real do proxy, reconexão ou todas as corridas. O patch é específico à versão
local; atualizações do pacote podem invalidá-lo. Pode haver atualizações
extras enquanto o menu está vazio; não há garantia de que um menu ainda em
construção visual corresponda exatamente ao cache, ou que falhas anteriores de
atualização sejam recuperadas sem novo sinal.

SHA-256 do arquivo original observado: `2ba944df1229840b66b4284ed5f409c07c42a23f2959d83e061d58cd146bea42`.
O hash é conferido a cada execução, porque a cópia de trabalho usada nos
testes é o arquivo instalado no momento.

## Executar o teste

```sh
python3 experimental/zorin-empty-menu/run-test.py
```

O script localiza a extensão instalada, copia `dbusMenu.js` para um diretório
temporário, aplica `dbusMenu.patch` nessa cópia e executa o teste GJS contra
as duas revisões. Quando a extensão não está instalada, ou quando o patch não
se aplica, ele informa `SKIP` e termina com sucesso — um sistema sem a
extensão (ou a CI) não falha por isso.

## Experimento com sinais reais da ponte

Execute na raiz do projeto, depois de construir as bibliotecas A/B existentes:

```sh
GIO_USE_VFS=local dbus-run-session -- gjs -m experimental/zorin-empty-menu/real-bridge-test.js \
  "$PWD/build/dbusmenu-properties-experiment/ab/control/libdarling-status-notifier.so" control \
  "$PWD/build/dbusmenu-properties-experiment/ab/corrected/libdarling-status-notifier.so" experimental \
  "$PWD/build/dbusmenu-properties-experiment/ab/corrected/libdarling-status-notifier.so" hidden
```

O teste usa barramento privado, processo próprio da ponte e `PropertyStore`,
`DbusMenuItem` e `DBusClient` extraídos da extensão instalada, inclusive os
métodos originais de sinal, layout, propriedades e ativação. Chamadas
GetLayout/GetGroupProperties e sinais vêm da ponte real. No controle, três
títulos novos permanecem vazios após ativação: somente LayoutUpdated é
enviado e, para IDs reaproveitados, o importador não solicita propriedades
sem a flag correspondente. Na experimental, ambos sinais são adiados enquanto
inativo; a ativação força layout e as propriedades são buscadas, atualizando
os três títulos. IDs e flags visível/habilitado permanecem estáveis. Com os
quatro ocultos, ambos sinais também são adiados; ativação forçada atualiza
títulos, mas não torna os itens visíveis.

Limitações: não carrega o Shell nem sua view/proxy real; adapta registro
GObject, emissão de eventos, cancelamento e agendamento idle, e usa
Gio.DBusProxy como transporte. A ativação é forçada por `active = true`,
inclusive no controle negativo oculto, não demonstra que um popup vazio
realmente abriria. Não testa AboutToShow, atores, processos existentes, nem
temporizações/races gerais; usa esperas fixas. A entrada representa snapshots
sintéticos, não tráfego do cliente. As bibliotecas são artefatos
preexistentes, não o binário de produção instalado.

## Instalação manual posterior e rollback

Não aplicar automaticamente. Faça backup fora da extensão, confira o hash
original acima e a compatibilidade com o pacote instalado. Uma opção
administrativa é aplicar `patch --dry-run -p1 -d
/usr/share/gnome-shell/extensions/zorin-appindicator@zorinos.com <
dbusMenu.patch`, depois, somente se correto e autorizado, repetir sem
`--dry-run` com privilégios administrativos. Isso altera arquivo gerenciado
pelo pacote; atualizações poderão sobrescrevê-lo. Para rollback, restaure o
backup exato ou reinstale o pacote original e confira seu hash/versão. A troca
em disco não altera necessariamente o código já carregado; ativação e
rollback efetivos exigem recarregar a extensão ou reiniciar a sessão por
procedimento apropriado, com possível interrupção do tray. Nenhuma dessas
ações foi executada aqui.

## Relação com a ponte do projeto

Este patch conserta um defeito do **consumidor** (a extensão do Zorin). A
ponte do projeto, em `tools/darling-dbus-menu.c`, tem um defeito independente:
as alterações de propriedades de itens existentes não são sinalizadas com
`ItemsPropertiesUpdated`. A variante experimental
`experimental/dbusmenu-properties/darling-dbus-menu.c` corrige isso, e ambas
as correções são necessárias em conjunto: o sinal de propriedades só é
processado quando a extensão consegue abrir o popup.

Nenhuma das duas correções substitui o patch de produção
`patches/cocotron.patch`; ambas permanecem experimentais e opt-in.
