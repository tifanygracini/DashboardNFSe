// Desenha os gráficos da página com as cores da marca, acompanhando o tema claro/escuro do navegador.
// Cada gráfico é um <div class="grafico" data-fonte="ID"> com os dados num <script type="application/json" id="ID">.
(function () {
  "use strict";
  if (!window.Plotly) return;
  const escuro = window.matchMedia("(prefers-color-scheme: dark)");
  const graficos = [];

  document.querySelectorAll(".grafico[data-fonte]").forEach(function (alvo) {
    const bloco = document.getElementById(alvo.dataset.fonte);
    if (bloco) graficos.push({ alvo: alvo, dados: JSON.parse(bloco.textContent) });
  });

  function desenhar() {
    const modo = escuro.matches ? "dark" : "light";
    const texto = escuro.matches ? "#EEF2F7" : "#153157";
    graficos.forEach(function (g) {
      const fig = JSON.parse(JSON.stringify(g.dados.figura));
      const cores = g.dados.cores[modo] || {};
      fig.data.forEach(function (t) {
        const cor = cores[t.name];
        if (!cor) return;
        t.marker = Object.assign({}, t.marker, { color: cor });
        if (t.type === "scatter") t.line = Object.assign({}, t.line, { color: cor });
      });
      fig.layout.font = Object.assign({}, fig.layout.font, { color: texto });
      fig.layout.autosize = true;
      window.Plotly.react(g.alvo, fig.data, fig.layout, { responsive: true, displaylogo: false,
        modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"] });
    });
  }

  desenhar();
  escuro.addEventListener("change", desenhar);
})();

// Seletor de empresa: escolher já aplica (sem precisar clicar em Aplicar).
document.querySelectorAll("select[data-enviar]").forEach(function (s) {
  s.addEventListener("change", function () { if (s.form) s.form.submit(); });
});
