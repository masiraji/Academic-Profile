/* Co-author Network Visualization using D3 v7 */
function initNetwork(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const width = container.clientWidth || 900;
  const height = 520;

  const countryColors = {
    "Malaysia":    "#1a6fc4",
    "Germany":     "#e63946",
    "USA":         "#2a9d8f",
    "Netherlands": "#f4a261",
    "Hungary":     "#9b5de5",
    "Bangladesh":  "#e76f51"
  };

  // Build nodes
  const centerNode = {
    id: "Siraji M.A.", name: "Mushfiqul Anwar Siraji",
    affiliation: "North South University", country: "Bangladesh",
    isSelf: true, papers: CV.publications.length
  };

  const coauthorNodes = CV.coauthors.map(c => ({
    ...c,
    isSelf: false,
    weight: c.papers.length || 0.5
  }));

  const nodes = [centerNode, ...coauthorNodes];

  // Build edges: Siraji ↔ each co-author
  const links = CV.coauthors
    .filter(c => c.papers.length > 0)
    .map(c => ({
      source: "Siraji M.A.",
      target: c.id,
      weight: c.papers.length
    }));

  // Also add co-author ↔ co-author links for shared papers
  const coEdges = [];
  CV.publications.forEach(pub => {
    const co = pub.coauthorIds;
    for (let i = 0; i < co.length; i++) {
      for (let j = i + 1; j < co.length; j++) {
        coEdges.push({ source: co[i], target: co[j], weight: 0.5 });
      }
    }
  });

  const allLinks = [...links, ...coEdges];

  const svg = d3.select(`#network-svg`)
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet");

  // Zoom
  const g = svg.append("g");
  svg.call(d3.zoom().scaleExtent([0.4, 3]).on("zoom", e => g.attr("transform", e.transform)));

  const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(allLinks).id(d => d.id)
      .distance(d => d.weight > 1 ? 80 : 120)
      .strength(d => d.weight > 1 ? 0.6 : 0.3))
    .force("charge", d3.forceManyBody().strength(-220))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide(d => d.isSelf ? 32 : 20));

  // Links
  const link = g.append("g").selectAll("line")
    .data(allLinks).join("line")
    .attr("stroke", d => d.weight >= 1 ? "rgba(100,140,200,.35)" : "rgba(200,210,230,.25)")
    .attr("stroke-width", d => d.weight >= 1 ? Math.sqrt(d.weight) * 1.4 : 0.8);

  // Nodes
  const node = g.append("g").selectAll("g")
    .data(nodes).join("g")
    .attr("cursor", "pointer")
    .call(d3.drag()
      .on("start", (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on("end", (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }));

  node.append("circle")
    .attr("r", d => d.isSelf ? 28 : Math.max(8, (d.papers?.length || 0.5) * 3 + 8))
    .attr("fill", d => d.isSelf ? "#1a3a5c" : countryColors[d.country] || "#aaa")
    .attr("stroke", d => d.isSelf ? "#fff" : "rgba(255,255,255,.7)")
    .attr("stroke-width", d => d.isSelf ? 3 : 1.5)
    .attr("opacity", d => d.isSelf ? 1 : 0.88);

  // Self label
  node.filter(d => d.isSelf).append("text")
    .text("MAS")
    .attr("text-anchor", "middle")
    .attr("dy", "0.35em")
    .attr("fill", "white")
    .attr("font-weight", "700")
    .attr("font-size", "11px")
    .attr("font-family", "Inter, sans-serif")
    .attr("pointer-events", "none");

  // Co-author labels
  node.filter(d => !d.isSelf && (d.papers?.length || 0) >= 2).append("text")
    .text(d => d.id.split(" ")[0])
    .attr("text-anchor", "middle")
    .attr("dy", d => (Math.max(8, (d.papers?.length || 0.5) * 3 + 8)) + 13)
    .attr("fill", "#4a5568")
    .attr("font-size", "10px")
    .attr("font-family", "Inter, sans-serif")
    .attr("pointer-events", "none");

  // Tooltip
  const tooltip = document.getElementById("network-tooltip");

  node.on("mouseover", function(e, d) {
    d3.select(this).select("circle")
      .attr("stroke-width", 3)
      .attr("stroke", "#1a6fc4");

    tooltip.style.display = "block";
    tooltip.innerHTML = d.isSelf
      ? `<strong>${d.name}</strong><br>${d.affiliation}`
      : `<strong>${d.name || d.id}</strong><br>${d.affiliation || ""}<br>
         <span style="opacity:.7">${d.country}${d.papers?.length ? " · " + d.papers.length + " paper" + (d.papers.length > 1 ? "s" : "") : ""}</span>`;

    const rect = container.getBoundingClientRect();
    tooltip.style.left = (e.clientX - rect.left + 12) + "px";
    tooltip.style.top  = (e.clientY - rect.top  - 20) + "px";
  })
  .on("mousemove", function(e) {
    const rect = container.getBoundingClientRect();
    tooltip.style.left = (e.clientX - rect.left + 12) + "px";
    tooltip.style.top  = (e.clientY - rect.top  - 20) + "px";
  })
  .on("mouseout", function(e, d) {
    d3.select(this).select("circle")
      .attr("stroke-width", d.isSelf ? 3 : 1.5)
      .attr("stroke", d.isSelf ? "#fff" : "rgba(255,255,255,.7)");
    tooltip.style.display = "none";
  });

  simulation.on("tick", () => {
    link
      .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });

  // Legend
  const legendEl = document.getElementById("network-legend");
  if (legendEl) {
    let html = "<h5>Country</h5>";
    Object.entries(countryColors).forEach(([country, color]) => {
      html += `<div class="legend-item"><div class="legend-dot" style="background:${color}"></div><span>${country}</span></div>`;
    });
    legendEl.innerHTML = html;
  }
}
