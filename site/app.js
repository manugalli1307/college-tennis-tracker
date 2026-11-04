(function () {
  "use strict";

  var DATA = {};
  var app = document.getElementById("main");
  var homeTab = null;
  var tourFilter = "all";
  var FILTERS = [["all", "All"], ["M15", "M15"], ["M25", "M25"], ["challenger", "Challengers"], ["atp", "ATP Tour"]];
  function passes(t) {
    if (tourFilter === "all") return true;
    if (tourFilter === "challenger") return t.tour === "ATP Challenger";
    if (tourFilter === "atp") return t.tour === "ATP Tour";
    return t.category === tourFilter;
  }
  function isoDaysAgo(n) {
    var d = new Date(); d.setDate(d.getDate() - n);
    return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
  }
  function isRecent(t) { return t.end >= isoDaysAgo(14); }
  function filterBar() {
    return '<div class="chips" role="group" aria-label="Filter tournaments">' + FILTERS.map(function (f) {
      return '<button type="button" data-filter="' + f[0] + '" aria-pressed="' + (tourFilter === f[0]) + '">' + f[1] + "</button>";
    }).join("") + "</div>";
  }
  function bindFilters() {
    Array.prototype.forEach.call(app.querySelectorAll("[data-filter]"), function (b) {
      b.addEventListener("click", function () { tourFilter = b.getAttribute("data-filter"); route(true); });
    });
  }

  // ---------- follows (saved in this browser only) ----------
  function loadFollows() {
    try { var f = JSON.parse(localStorage.getItem("ctot-follows") || "{}"); return { p: f.p || [], t: f.t || [] }; }
    catch (e) { return { p: [], t: [] }; }
  }
  function saveFollows(f) { try { localStorage.setItem("ctot-follows", JSON.stringify(f)); } catch (e) { /* private mode */ } }
  function isFollowing(kind, id) { return loadFollows()[kind].indexOf(id) >= 0; }
  function followButton(kind, id) {
    var on = isFollowing(kind, id);
    return '<button type="button" class="follow" data-follow="' + kind + ":" + esc(id) + '" aria-pressed="' + on + '">' + (on ? "★ Following" : "☆ Follow") + "</button>";
  }
  function bindFollow() {
    Array.prototype.forEach.call(app.querySelectorAll("[data-follow]"), function (b) {
      b.addEventListener("click", function () {
        var parts2 = b.getAttribute("data-follow").split(":"), kind = parts2[0], id = parts2.slice(1).join(":");
        var f = loadFollows(), i = f[kind].indexOf(id);
        if (i >= 0) f[kind].splice(i, 1); else f[kind].push(id);
        saveFollows(f);
        b.setAttribute("aria-pressed", i < 0);
        b.textContent = i < 0 ? "★ Following" : "☆ Follow";
      });
    });
  }

  // ---------- helpers ----------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function plain(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }
  function slug(s) { return plain(s).replace(/ /g, "-"); }
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function parts(iso) { var p = iso.split("-"); return { y: +p[0], m: +p[1] - 1, d: +p[2] }; }
  function fmtRange(a, b) {
    var s = parts(a), e = parts(b);
    if (s.m === e.m) return MONTHS[s.m] + " " + s.d + "–" + e.d;
    return MONTHS[s.m] + " " + s.d + " – " + MONTHS[e.m] + " " + e.d;
  }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : many || one + "s"); }
  function fetchJSON(name) {
    return fetch("data/" + name, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(name + " " + r.status);
      return r.json();
    });
  }

  // ---------- data ----------
  function index() {
    DATA.draws = DATA.draws || {}; DATA.ranks = DATA.ranks || {};
    DATA.playerById = {}; DATA.tById = {}; DATA.teams = {};
    DATA.entriesByT = {}; DATA.entriesByP = {}; DATA.matchesByT = {}; DATA.matchesByP = {};
    DATA.players.forEach(function (p) {
      DATA.playerById[p.id] = p;
      var key = slug(p.school);
      var t = DATA.teams[key] || (DATA.teams[key] = { slug: key, school: p.school, rank: 999, players: [] });
      var r = parseInt(p.team_rank, 10);
      if (!isNaN(r) && r < t.rank) t.rank = r;
      t.players.push(p);
    });
    DATA.tournaments.forEach(function (t) { DATA.tById[t.id] = t; });
    DATA.entries.forEach(function (e) {
      (DATA.entriesByT[e.tournament] = DATA.entriesByT[e.tournament] || []).push(e);
      (DATA.entriesByP[e.player] = DATA.entriesByP[e.player] || []).push(e);
    });
    DATA.matches.forEach(function (m) {
      (DATA.matchesByT[m.tournament] = DATA.matchesByT[m.tournament] || []).push(m);
      ["p1", "p2"].forEach(function (k) {
        if (!m[k]) return;
        m[k].roster.forEach(function (pid) {
          (DATA.matchesByP[pid] = DATA.matchesByP[pid] || []).push({ m: m, side: k === "p1" ? 1 : 2 });
        });
      });
    });
  }
  function teamList() {
    return Object.keys(DATA.teams).map(function (k) { return DATA.teams[k]; })
      .sort(function (a, b) { return a.rank - b.rank || a.school.localeCompare(b.school); });
  }
  function byStatus(status) {
    return DATA.tournaments.filter(function (t) { return t.status === status; });
  }

  // ---------- pieces ----------
  function setCell(raw) {
    var m = /^(\d+)\((\d+)\)$/.exec(raw || "");
    return m ? m[1] + "<sup>" + m[2] + "</sup>" : esc(raw || "");
  }
  function setsHTML(sets, flip, cls) {
    if (!sets || !sets.length) return "";
    return '<span class="sets ' + cls + '" aria-label="Score">' + sets.map(function (s) {
      var a = flip ? s[1] : s[0], b = flip ? s[0] : s[1];
      return "<span>" + setCell(a) + "–" + setCell(b) + "</span>";
    }).join("") + "</span>";
  }
  function playerLink(p) {
    return '<a href="#/player/' + esc(p.id) + '">' + esc(p.name) + "</a>";
  }
  function tournamentLink(t) {
    return '<a href="#/tournament/' + esc(t.id) + '">' + esc(t.name) + "</a>";
  }
  function oppHTML(o) {
    if (!o) return "<span class=\"muted\">Bye</span>";
    var name = esc(o.name || "TBD");
    if (o.roster && o.roster.length && DATA.playerById[o.roster[0]]) {
      name = '<a href="#/player/' + esc(o.roster[0]) + '">' + name + "</a>";
    }
    var extra = [o.country, o.seed ? "seed " + o.seed : ""].filter(Boolean).join(", ");
    return name + (extra ? ' <span class="muted">(' + esc(extra) + ")</span>" : "") +
      (o.rank ? ' <span class="rk" title="Current ATP singles ranking">ATP #' + esc(o.rank) + "</span>" : "");
  }

  // One row for a player in an event; match may be null (just entered)
  function playerRow(p, ent, hit, showEvent, t) {
    var who = '<div class="row__who">' + playerLink(p) +
      '<div class="row__sub"><a href="#/team/' + esc(slug(p.school)) + '">' + esc(p.school) + "</a></div></div>";
    var mid, right = "";
    if (hit) {
      var m = hit.m, me = hit.side === 1 ? m.p1 : m.p2, opp = hit.side === 1 ? m.p2 : m.p1;
      var won = m.winner === hit.side, lost = m.winner && m.winner !== hit.side;
      var cls = won ? "wl--w" : lost ? "wl--l" : "wl--live";
      var label = won ? "W" : lost ? "L" : m.live ? "Live" : "–";
      mid = '<div class="row__vs"><span class="round">' + (showEvent && t ? tournamentLink(t) + " · " : "") +
        esc(m.draw === "Qualifying" ? "Qualifying " : "") + esc(m.round) + "</span>vs " + oppHTML(opp) + "</div>";
      right = '<div class="result">' + setsHTML(m.sets, hit.side === 2, won ? "sets--win" : lost ? "sets--loss" : "") +
        '<span class="wl ' + cls + '">' + label + "</span></div>";
    } else {
      var sec = ent ? ent.section.replace(/ Direct Acceptance$/i, "") : "";
      mid = '<div class="row__vs">' + (showEvent && t ? '<span class="round">' + tournamentLink(t) + "</span>" : "") +
        '<span class="entered">' + (sec ? "Entered in " + esc(sec.toLowerCase()) : "Entered") + "</span></div>";
    }
    return '<li class="row">' + who + mid + right + "</li>";
  }

  function entryFor(tid, pid) {
    return (DATA.entriesByT[tid] || []).filter(function (e) { return e.player === pid; })[0];
  }
  function hitsFor(tid, pid) {
    return (DATA.matchesByP[pid] || []).filter(function (h) { return h.m.tournament === tid; });
  }

  function statusTag(t) {
    if (t.status === "current") return '<span class="tag tag--now">In progress</span>';
    if (t.status === "upcoming") return '<span class="tag tag--next">Starts ' + MONTHS[parts(t.start).m] + " " + parts(t.start).d + "</span>";
    return '<span class="tag">Finished</span>';
  }

  // players = optional Set of ids to limit to; all = show every match not just the latest
  function eventBlock(t, only, all, noHead) {
    var ids = [];
    (DATA.entriesByT[t.id] || []).forEach(function (e) { if (ids.indexOf(e.player) < 0) ids.push(e.player); });
    (DATA.matchesByT[t.id] || []).forEach(function (m) {
      ["p1", "p2"].forEach(function (k) { if (m[k]) m[k].roster.forEach(function (pid) { if (ids.indexOf(pid) < 0) ids.push(pid); }); });
    });
    ids = ids.filter(function (id) { return DATA.playerById[id] && (!only || only[id]); });
    if (!ids.length) return "";
    ids.sort(function (a, b) {
      var A = DATA.playerById[a], B = DATA.playerById[b];
      return (parseInt(A.team_rank, 10) || 99) - (parseInt(B.team_rank, 10) || 99) || A.name.localeCompare(B.name);
    });
    var seen = [];
    var rows = ids.map(function (pid) {
      var p = DATA.playerById[pid], ent = entryFor(t.id, pid), hits = hitsFor(t.id, pid);
      if (!hits.length) return playerRow(p, ent, null, false, t);
      if (all) return hits.map(function (h) {
        if (seen.indexOf(h.m) >= 0) return "";
        seen.push(h.m);
        return playerRow(p, ent, h, false, t);
      }).join("");
      var live = hits.filter(function (h) { return h.m.live; })[0];
      return playerRow(p, ent, live || hits[hits.length - 1], false, t);
    }).join("");
    if (noHead) return '<section class="event"><ul class="rows">' + rows + "</ul></section>";
    return '<section class="event"><div class="event__head"><h3>' + tournamentLink(t) + "</h3>" + statusTag(t) +
      '<div class="event__meta"><span>' + esc(fmtRange(t.start, t.end)) + "</span><span>" + esc(t.category) + "</span>" +
      (t.country ? "<span>" + esc(t.country) + "</span>" : "") + "<span>" + plural(ids.length, "player") + "</span></div></div>" +
      '<ul class="rows">' + rows + "</ul></section>";
  }

  function empty(msg) { return '<p class="empty">' + msg + "</p>"; }

  // ---------- pages ----------
  function pageHome() {
    var cur = byStatus("current").filter(passes), nxt = byStatus("upcoming").filter(passes),
      past = byStatus("past").filter(isRecent).filter(passes).reverse();
    var tabs = [
      { id: "current", label: "Playing now", list: cur, none: "No roster players are in an event right now. Check Next up for who is entered." },
      { id: "upcoming", label: "Next up", list: nxt, none: "No entry lists are published yet for roster players. Lists usually appear about two weeks before an event." },
      { id: "past", label: "Last two weeks", list: past, none: "No finished events in the last two weeks include roster players." }
    ];
    function hasPlayers(t) { return eventBlock(t) !== ""; }
    if (!homeTab) homeTab = tabs.filter(function (t) { return t.list.some(hasPlayers); })[0];
    homeTab = homeTab ? tabs.filter(function (t) { return t.id === homeTab.id; })[0] : tabs[0];

    var live = cur.reduce(function (n, t) { return n + (DATA.entriesByT[t.id] || []).length; }, 0);
    var upc = nxt.reduce(function (n, t) { return n + (DATA.entriesByT[t.id] || []).length; }, 0);
    var html = '<section class="hero"><h1>Top college players,<br>pro tournaments</h1>' +
      '<p class="lede">Men from the top 30 Division I teams at ITF M15 and M25 events, ATP Challengers and the ATP Tour: who is playing now, who is entered next, and how they did.</p>' +
      '<div class="hero__count"><span><b>' + live + "</b>in events now</span><span><b>" + upc + "</b>entered in upcoming events</span><span><b>" +
      DATA.players.length + "</b>players on " + teamList().length + " teams</span></div></section>";
    html += filterBar() + '<div class="tabs" role="tablist">' + tabs.map(function (t) {
      return '<button role="tab" data-tab="' + t.id + '" aria-selected="' + (t.id === homeTab.id) + '">' + t.label + "</button>";
    }).join("") + "</div>";
    var blocks = homeTab.list.map(function (t) { return eventBlock(t); }).join("");
    html += blocks || empty(homeTab.none);
    app.innerHTML = html;
    bindFilters();
    Array.prototype.forEach.call(app.querySelectorAll("[data-tab]"), function (b) {
      b.addEventListener("click", function () {
        homeTab = tabs.filter(function (t) { return t.id === b.getAttribute("data-tab"); })[0];
        pageHome();
      });
    });
  }

  function pageTeams() {
    app.innerHTML = "<h1>Teams</h1><p class=\"lede\">The top 30 Division I men's teams, by team ranking.</p>" +
      '<ul class="grid section">' + teamList().map(function (t) {
        var active = t.players.filter(function (p) { return (DATA.entriesByP[p.id] || []).length; }).length;
        return '<li><a href="#/team/' + esc(t.slug) + '"><span><span class="num">' + (t.rank < 999 ? t.rank + " " : "") + "</span><strong>" +
          esc(t.school) + '</strong></span><span class="muted">' + (active ? active + " on tour" : plural(t.players.length, "player")) + "</span></a></li>";
      }).join("") + "</ul>";
  }

  function pageTeam(key) {
    var team = DATA.teams[key];
    if (!team) return notFound("team");
    var only = {};
    team.players.forEach(function (p) { only[p.id] = true; });
    var order = { current: 0, upcoming: 1, past: 2 };
    var events = DATA.tournaments.slice().sort(function (a, b) {
      return order[a.status] - order[b.status] || (a.status === "past" ? b.start.localeCompare(a.start) : a.start.localeCompare(b.start));
    });
    var blocks = events.map(function (t) { return eventBlock(t, only); }).join("");
    var roster = team.players.slice().sort(function (a, b) { return a.name.localeCompare(b.name); }).map(function (p) {
      var n = (DATA.entriesByP[p.id] || []).length;
      return '<li><a href="#/player/' + esc(p.id) + '"><strong>' + esc(p.name) + '</strong><span class="muted">' +
        esc(p.class || "") + (n ? (p.class ? " · " : "") + plural(n, "event") : "") + "</span></a></li>";
    }).join("");
    app.innerHTML = '<p class="crumbs"><a href="#/teams">Teams</a></p><h1>' + esc(team.school) + "</h1>" + followButton("t", team.slug) +
      (team.rank < 999 ? '<div class="facts"><span>Team ranking <b>' + team.rank + "</b></span><span><b>" + team.players.length + "</b> players</span></div>" : "") +
      '<div class="section"><h2>On tour</h2>' + (blocks || empty("No players from this team are in ITF, Challenger or ATP events in the last two weeks or the next three.")) + "</div>" +
      '<div class="section"><h2>Roster</h2><ul class="grid">' + roster + "</ul></div>";
    bindFollow();
  }

  function pagePlayer(id) {
    var p = DATA.playerById[id];
    if (!p) return notFound("player");
    var hits = DATA.matchesByP[id] || [];
    var w = 0, l = 0;
    hits.forEach(function (h) { if (h.m.winner === h.side) w++; else if (h.m.winner) l++; });
    var tids = [];
    (DATA.entriesByP[id] || []).forEach(function (e) { if (tids.indexOf(e.tournament) < 0) tids.push(e.tournament); });
    hits.forEach(function (h) { if (tids.indexOf(h.m.tournament) < 0) tids.push(h.m.tournament); });
    var ts = tids.map(function (x) { return DATA.tById[x]; }).filter(Boolean);
    var upcoming = ts.filter(function (t) { return t.status === "upcoming"; }).sort(function (a, b) { return a.start.localeCompare(b.start); });
    var played = ts.filter(function (t) { return t.status !== "upcoming"; }).sort(function (a, b) { return b.start.localeCompare(a.start); });
    var only = {}; only[id] = true;
    var html = '<p class="crumbs"><a href="#/team/' + esc(slug(p.school)) + '">' + esc(p.school) + "</a></p><h1>" + esc(p.name) + "</h1>" +
      '<div class="facts">' + (p.class ? "<span><b>" + esc(p.class) + "</b></span>" : "") +
      (p.hometown ? "<span>" + esc(p.hometown) + "</span>" : "") + "</div>";
    var rk = DATA.ranks[id];
    if (rk && rk.rank) html += '<div class="facts"><span>ATP singles ranking <b>#' + esc(rk.rank) + "</b></span></div>";
    html += followButton("p", id);
    if (w + l) html += '<p class="record"><b>' + w + "–" + l + '</b>in singles matches tracked on this site</p>';
    html += '<div class="section"><h2>Coming up</h2>' +
      (upcoming.length ? upcoming.map(function (t) { return eventBlock(t, only); }).join("") : empty("Not on any published entry list yet.")) + "</div>";
    html += '<div class="section"><h2>Playing and results</h2>' +
      (played.length ? played.map(function (t) { return eventBlock(t, only, true); }).join("") : empty("No matches tracked yet.")) + "</div>";
    app.innerHTML = html;
    bindFollow();
  }

  function tournamentList(list) {
    return '<ul class="grid">' + list.map(function (t) {
      var n = new Set((DATA.entriesByT[t.id] || []).map(function (e) { return e.player; })).size;
      return '<li><a href="#/tournament/' + esc(t.id) + '"><span><strong>' + esc(t.name) + '</strong><br><span class="muted">' +
        esc(fmtRange(t.start, t.end)) + " · " + esc(t.category) + "</span></span><span class=\"muted\">" + (n ? plural(n, "player") : "") + "</span></a></li>";
    }).join("") + "</ul>";
  }
  function pageTournaments() {
    var html = "<h1>Tournaments</h1><p class=\"lede\">ITF M15 and M25 events, ATP Challengers and the ATP Tour. Finished events stay here for the whole season.</p>" + filterBar();
    var all = DATA.tournaments.filter(passes);
    [["current", "Playing now"], ["upcoming", "Next up"]].forEach(function (g) {
      var list = all.filter(function (t) { return t.status === g[0]; });
      if (list.length) html += '<div class="section"><h2>' + g[1] + "</h2>" + tournamentList(list) + "</div>";
    });
    var past = all.filter(function (t) { return t.status === "past"; }).reverse();
    var recent = past.filter(isRecent), older = past.filter(function (t) { return !isRecent(t); });
    if (recent.length) html += '<div class="section"><h2>Last two weeks</h2>' + tournamentList(recent) + "</div>";
    if (older.length) html += '<details class="section"><summary><h2>Earlier this season (' + older.length + ")</h2></summary>" + tournamentList(older) + "</details>";
    if (!all.length) html += empty("No tournaments match this filter right now.");
    app.innerHTML = html;
    bindFilters();
  }

  // The full draw, with college players highlighted
  function drawHTML(t) {
    var ms = DATA.draws[t.id];
    if (!ms || !ms.length) return "";
    var groups = [], idx = {};
    ms.forEach(function (m) {
      var key = m.draw + "|" + m.round;
      if (idx[key] === undefined) { idx[key] = groups.length; groups.push({ draw: m.draw, round: m.round, list: [] }); }
      groups[idx[key]].list.push(m);
    });
    function side(o, won, sets, flip) {
      if (!o) return '<div class="dm__p"><span class="muted">Bye</span></div>';
      var hl = o.roster && o.roster.length && DATA.playerById[o.roster[0]];
      var nm = hl ? '<a href="#/player/' + esc(o.roster[0]) + '">' + esc(o.name) + "</a>" : esc(o.name || "TBD");
      var info = [o.seed ? "(" + esc(o.seed) + ")" : "", o.rank ? "ATP #" + esc(o.rank) : ""].filter(Boolean).join(" ");
      return '<div class="dm__p' + (won ? " dm__p--w" : "") + (hl ? " dm__p--hl" : "") + '"><span class="dm__n">' + nm +
        (hl ? ' <span class="dm__s">' + esc(DATA.playerById[o.roster[0]].school) + "</span>" : "") +
        (info ? ' <span class="muted">' + info + "</span>" : "") + '</span><span class="dm__sc">' +
        (sets || []).map(function (st) { return "<span>" + setCell(flip ? st[1] : st[0]) + "</span>"; }).join("") + "</span></div>";
    }
    var html = '<div class="section"><h2>Draw</h2><p class="muted">College players are highlighted.</p>';
    groups.forEach(function (g) {
      html += '<h3 class="dr">' + esc((g.draw === "Qualifying" ? "Qualifying · " : "") + g.round) + '</h3><div class="dm-grid">' +
        g.list.map(function (m) {
          return '<div class="dm' + (m.live ? " dm--live" : "") + '">' + side(m.p1, m.winner === 1, m.sets, false) +
            side(m.p2, m.winner === 2, m.sets, true) + "</div>";
        }).join("") + "</div>";
    });
    return html + "</div>";
  }

  function pageTournament(id) {
    var t = DATA.tById[id];
    if (!t) return notFound("tournament");
    var block = eventBlock(t, null, true, true);
    var html = '<p class="crumbs"><a href="#/tournaments">Tournaments</a></p><h1>' + esc(t.name) + "</h1>" +
      '<div class="facts"><span><b>' + esc(fmtRange(t.start, t.end)) + "</b></span><span>" + esc(t.category) + "</span>" +
      (t.country ? "<span>" + esc(t.country) + "</span>" : "") + "<span>" + statusTag(t) + "</span>" +
      '<span><a href="' + esc(t.url) + '" rel="noopener" target="_blank">' + (/^ATP/.test(t.tour || "") ? "Draws on tennisexplorer.com" : "Draws on itftennis.com") + "</a></span></div>";
    html += '<div class="section">' + (block || empty(t.status === "upcoming"
      ? "No roster players are on the entry list yet. Lists usually appear about two weeks before the event."
      : "No roster players found in this event.")) + "</div>";
    html += drawHTML(t);
    app.innerHTML = html;
  }

  function pageFollowing() {
    var f = loadFollows(), only = {}, n = 0;
    f.p.forEach(function (id) { if (DATA.playerById[id]) { only[id] = true; n++; } });
    f.t.forEach(function (k) { if (DATA.teams[k]) DATA.teams[k].players.forEach(function (p) { only[p.id] = true; n++; }); });
    var html = "<h1>Following</h1>";
    if (!n) {
      app.innerHTML = html + empty("You aren't following anyone yet. Open a player or a team and press Follow. Your list is saved in this browser on this device only.");
      return;
    }
    html += '<p class="lede">Your followed players and teams. This list is saved in this browser only.</p>';
    var shown = false;
    [["current", "Playing now"], ["upcoming", "Next up"], ["past", "Recent results"]].forEach(function (g) {
      var list = DATA.tournaments.filter(function (t) { return t.status === g[0] && (g[0] !== "past" || isRecent(t)); });
      if (g[0] === "past") list = list.slice().reverse();
      var blocks = list.map(function (t) { return eventBlock(t, only); }).join("");
      if (blocks) { shown = true; html += '<div class="section"><h2>' + g[1] + "</h2>" + blocks + "</div>"; }
    });
    if (!shown) html += empty("None of them are in an event right now or entered in the next three weeks.");
    var people = Object.keys(only).map(function (id) { return DATA.playerById[id]; }).filter(Boolean)
      .sort(function (a, b) { return a.name.localeCompare(b.name); });
    html += '<div class="section"><h2>Who you follow</h2><ul class="grid">' + people.map(function (p) {
      return '<li><a href="#/player/' + esc(p.id) + '"><strong>' + esc(p.name) + '</strong><span class="muted">' + esc(p.school) + "</span></a></li>";
    }).join("") + "</ul></div>";
    app.innerHTML = html;
  }

  function pageRanking() {
    var list = DATA.players.map(function (p) { return { p: p, r: DATA.ranks[p.id] }; })
      .filter(function (x) { return x.r && x.r.rank; })
      .sort(function (a, b) { return a.r.rank - b.r.rank; });
    var html = "<h1>College ranking</h1><p class=\"lede\">Roster players by current ATP singles ranking. Only players we have seen in Challenger or ATP events so far have a ranking here; more fill in as the season goes.</p>";
    html += list.length ? '<ol class="rank">' + list.map(function (x) {
      return '<li><span class="rank__n">#' + esc(x.r.rank) + '</span><a href="#/player/' + esc(x.p.id) + '"><strong>' + esc(x.p.name) +
        '</strong></a><span class="muted">' + esc(x.p.school) + "</span></li>";
    }).join("") + "</ol>" : empty("No rankings yet. They appear after the next update.");
    app.innerHTML = html;
  }

  function notFound(what) {
    app.innerHTML = "<h1>Not found</h1>" + empty("We couldn't find that " + esc(what) + ". It may have aged out of the two-week window. <a href=\"#/\">Back to this week</a>.");
  }

  // ---------- router ----------
  function route(keepScroll) {
    if (!DATA.players) return;
    var h = location.hash.replace(/^#\/?/, "");
    var seg = h.split("/");
    var page = seg[0] || "home", arg = decodeURIComponent(seg.slice(1).join("/"));
    Array.prototype.forEach.call(document.querySelectorAll("[data-nav]"), function (a) {
      var on = a.getAttribute("data-nav") === (page === "team" ? "teams" : page === "tournament" ? "tournaments" : page === "player" ? "teams" : page);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (page === "teams") pageTeams();
    else if (page === "team") pageTeam(arg);
    else if (page === "player") pagePlayer(arg);
    else if (page === "tournaments") pageTournaments();
    else if (page === "tournament") pageTournament(arg);
    else if (page === "following") pageFollowing();
    else if (page === "ranking") pageRanking();
    else pageHome();
    if (keepScroll !== true) window.scrollTo(0, 0);
    document.title = (page === "home" ? "" : (app.querySelector("h1") || {}).textContent + " – ") + "College Tennis on Tour";
  }

  // ---------- search ----------
  function setupSearch() {
    var q = document.getElementById("q"), box = document.getElementById("results");
    function close() { box.hidden = true; box.innerHTML = ""; }
    function run() {
      var term = plain(q.value);
      if (term.length < 2) return close();
      var words = term.split(" ");
      function hit(s) { var p = plain(s); return words.every(function (w) { return p.indexOf(w) >= 0; }); }
      var pl = DATA.players.filter(function (p) { return hit(p.name + " " + p.school); }).slice(0, 8);
      var tm = teamList().filter(function (t) { return hit(t.school); }).slice(0, 5);
      var tn = DATA.tournaments.filter(function (t) { return hit(t.name + " " + t.country); }).slice(0, 6);
      var html = "";
      if (pl.length) html += '<li class="group">Players</li>' + pl.map(function (p) {
        return '<li><a href="#/player/' + esc(p.id) + '">' + esc(p.name) + "<small>" + esc(p.school) + "</small></a></li>";
      }).join("");
      if (tm.length) html += '<li class="group">Teams</li>' + tm.map(function (t) {
        return '<li><a href="#/team/' + esc(t.slug) + '">' + esc(t.school) + "</a></li>";
      }).join("");
      if (tn.length) html += '<li class="group">Tournaments</li>' + tn.map(function (t) {
        return '<li><a href="#/tournament/' + esc(t.id) + '">' + esc(t.name) + "<small>" + esc(fmtRange(t.start, t.end)) + "</small></a></li>";
      }).join("");
      box.innerHTML = html || '<li class="search__empty">Nothing matches "' + esc(q.value) + '". Try a surname or a school.</li>';
      box.hidden = false;
    }
    q.addEventListener("input", run);
    q.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { close(); q.blur(); }
      if (e.key === "Enter") { var a = box.querySelector("a"); if (a) { location.hash = a.getAttribute("href"); q.value = ""; close(); } }
    });
    box.addEventListener("click", function (e) { if (e.target.closest("a")) { q.value = ""; close(); } });
    document.addEventListener("click", function (e) { if (!e.target.closest(".search")) close(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement !== q && !/input|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); q.focus(); }
    });
  }

  // ---------- start ----------
  app.innerHTML = '<p class="empty">Loading the latest entries and results…</p>';
  function optional(name, fallback) { return fetchJSON(name).catch(function () { return fallback; }); }
  Promise.all(["players.json", "tournaments.json", "entries.json", "matches.json", "meta.json"].map(fetchJSON)
    .concat([optional("draws.json", {}), optional("rankings.json", {})]))
    .then(function (r) {
      DATA.players = r[0]; DATA.tournaments = r[1]; DATA.entries = r[2]; DATA.matches = r[3]; DATA.meta = r[4];
      DATA.draws = r[5]; DATA.ranks = r[6];
      index();
      setupSearch();
      if (DATA.meta && DATA.meta.updated) {
        var d = new Date(DATA.meta.updated);
        document.getElementById("updated").textContent = "Last updated " + d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + ".";
      }
      window.addEventListener("hashchange", function () { route(); });
      route();
    })
    .catch(function () {
      app.innerHTML = "<h1>Data not available</h1>" + empty("The latest data couldn't be loaded. Reload the page in a minute; if it keeps happening, the daily update may have failed.");
    });
})();
