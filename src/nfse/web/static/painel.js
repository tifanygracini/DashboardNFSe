// Desenha o gráfico mensal com as cores da marca, acompanhando o tema claro/escuro do navegador.
(function () {
  "use strict";
  const alvo = document.getElementById("grafico-mensal");
  const bloco = document.getElementById("dados-grafico");
  if (!alvo || !bloco || !window.Plotly) return;
  const dados = JSON.parse(bloco.textContent);
  const escuro = window.matchMedia("(prefers-color-scheme: dark)");

  function desenhar() {
    const modo = escuro.matches ? "dark" : "light";
    const fig = JSON.parse(JSON.stringify(dados.figura));
    const cores = dados.cores[modo];
    fig.data.forEach(function (t) {
      if (cores[t.name]) t.marker = Object.assign({}, t.marker, { color: cores[t.name] });
    });
    const texto = escuro.matches ? "#EEF2F7" : "#153157";
    fig.layout.font = Object.assign({}, fig.layout.font, { color: texto });
    fig.layout.autosize = true;
    window.Plotly.react(alvo, fig.data, fig.layout, { responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"] });
  }

  desenhar();
  escuro.addEventListener("change", desenhar);
})();
