/* Global Collaboration Map using D3 v7 + TopoJSON */
async function initMap(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const width  = container.clientWidth || 900;
  const height = Math.round(width * 0.52);

  const svg = d3.select("#map-svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet");

  const projection = d3.geoNaturalEarth1()
    .scale(width / 6.2)
    .translate([width / 2, height / 2]);

  const path = d3.geoPath().projection(projection);

  // Fetch world topojson
  let world;
  try {
    world = await d3.json("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json");
  } catch(e) { console.warn("Map data load failed", e); return; }

  const countries = topojson.feature(world, world.objects.countries);

  // Build lookup: ISO numeric -> collaboration data
  const collabMap = {};
  CV.collaborationCountries.forEach(c => { collabMap[c.iso] = c; });

  // Graticule
  svg.append("path")
    .datum(d3.geoGraticule()())
    .attr("d", path)
    .attr("fill", "none")
    .attr("stroke", "rgba(100,140,200,.08)")
    .attr("stroke-width", 0.5);

  // Countries
  svg.append("g")
    .selectAll("path")
    .data(countries.features)
    .join("path")
    .attr("d", path)
    .attr("fill", d => collabMap[+d.id] ? "oklch(44% 0.13 240)" : "oklch(93% 0.02 240)")
    .attr("stroke", "white")
    .attr("stroke-width", 0.5)
    .attr("opacity", d => collabMap[+d.id] ? 0.85 : 1)
    .attr("cursor", d => collabMap[+d.id] ? "pointer" : "default")
    .on("mouseover", function(e, d) {
      const c = collabMap[+d.id];
      if (!c) return;
      d3.select(this).attr("fill", "oklch(34% 0.16 240)").attr("opacity", 1);
      showMapTooltip(e, c, container);
    })
    .on("mousemove", function(e, d) {
      const c = collabMap[+d.id];
      if (!c) return;
      moveMapTooltip(e, container);
    })
    .on("mouseout", function(e, d) {
      const c = collabMap[+d.id];
      if (!c) return;
      d3.select(this).attr("fill", "oklch(44% 0.13 240)").attr("opacity", 0.85);
      document.getElementById("map-tooltip").style.display = "none";
    });

  // Bubbles on collaboration countries
  svg.append("g")
    .selectAll("circle")
    .data(CV.collaborationCountries)
    .join("circle")
    .attr("cx", d => projection([d.lon, d.lat])[0])
    .attr("cy", d => projection([d.lon, d.lat])[1])
    .attr("r", d => Math.max(6, Math.sqrt(d.count) * 5))
    .attr("fill", "rgba(255,255,255,.25)")
    .attr("stroke", "white")
    .attr("stroke-width", 2)
    .attr("pointer-events", "none");

  // Country labels on bubbles
  svg.append("g")
    .selectAll("text")
    .data(CV.collaborationCountries)
    .join("text")
    .attr("x", d => projection([d.lon, d.lat])[0])
    .attr("y", d => projection([d.lon, d.lat])[1] - Math.max(6, Math.sqrt(d.count) * 5) - 5)
    .attr("text-anchor", "middle")
    .attr("fill", "white")
    .attr("font-size", "10px")
    .attr("font-weight", "700")
    .attr("font-family", "Inter, sans-serif")
    .attr("stroke", "oklch(44% 0.13 240)")
    .attr("stroke-width", "3px")
    .attr("paint-order", "stroke")
    .attr("pointer-events", "none")
    .text(d => d.name);

  // Home marker for Bangladesh
  const home = CV.collaborationCountries.find(c => c.name === "Bangladesh");
  if (home) {
    const [hx, hy] = projection([home.lon, home.lat]);
    svg.append("circle")
      .attr("cx", hx).attr("cy", hy).attr("r", 6)
      .attr("fill", "#e63946").attr("stroke", "white").attr("stroke-width", 2)
      .attr("pointer-events", "none");
  }
}

function showMapTooltip(e, c, container) {
  const tooltip = document.getElementById("map-tooltip");
  tooltip.style.display = "block";
  tooltip.innerHTML = `<strong>${c.name}</strong><br>
    <span style="opacity:.8">${c.count} collaborator${c.count > 1 ? "s" : ""}</span><br>
    <span style="opacity:.6;font-size:11px">${c.top.join(" · ")}</span>`;
  moveMapTooltip(e, container);
}

function moveMapTooltip(e, container) {
  const rect = container.getBoundingClientRect();
  const tooltip = document.getElementById("map-tooltip");
  tooltip.style.left = (e.clientX - rect.left + 12) + "px";
  tooltip.style.top  = (e.clientY - rect.top  - 20) + "px";
}
