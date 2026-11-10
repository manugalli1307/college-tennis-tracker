(function () {
  "use strict";

  var DATA = {};
  var app = document.getElementById("main");
  var homeTab = null;
  var tourFilter = "all";
  var homeView = "current";
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
    DATA.allPlayers = DATA.players.slice();
    DATA.players = DATA.allPlayers.filter(function (p) { return !p.alumni; });
    DATA.alumniAll = DATA.allPlayers.filter(function (p) { return p.alumni; });
    DATA.alumniTeams = {};
    DATA.alumniAll.forEach(function (p) {
      var k = slug(p.school);
      var t = DATA.alumniTeams[k] || (DATA.alumniTeams[k] = { slug: k, school: p.school, players: [] });
      t.players.push(p);
    });
    DATA.playerById = {}; DATA.tById = {}; DATA.teams = {};
    DATA.allPlayers.forEach(function (p) { DATA.playerById[p.id] = p; });
    DATA.entriesByT = {}; DATA.entriesByP = {}; DATA.matchesByT = {}; DATA.matchesByP = {};
    DATA.players.forEach(function (p) {
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
  function rkBadge(id, rank) {
    var r = rank || (DATA.ranks[id] && DATA.ranks[id].rank);
    return r ? ' <span class="rk" title="Current ATP singles ranking">ATP #' + esc(r) + "</span>" : "";
  }
  function alumTag(p) { return p && p.alumni ? ' <span class="tag tag--alum">Alumni</span>' : ""; }
  function alumLabel(p) { return p.colleges ? p.colleges : p.grad ? "Class of " + p.grad : p.last_season ? "Last season " + p.last_season : "Alumni"; }
  function schoolLink(p) {
    return p.alumni ? '<a href="#/alumni/' + esc(slug(p.school)) + '">' + esc(p.school) + " alumni</a>"
      : '<a href="#/team/' + esc(slug(p.school)) + '">' + esc(p.school) + "</a>";
  }
  function playerLink(p) {
    return '<a href="#/player/' + esc(p.id) + '">' + esc(p.name) + "</a>" + rkBadge(p.id) + alumTag(p);
  }
  function tournamentLink(t) {
    return '<a href="#/tournament/' + esc(t.id) + '">' + esc(t.name) + "</a>";
  }
  function oppHTML(o) {
    if (!o) return "<span class=\"muted\">Bye</span>";
    var name = esc(o.name || "TBD");
    if (o.roster && o.roster.length && DATA.playerById[o.roster[0]]) {
      name = '<a href="#/player/' + esc(o.roster[0]) + '">' + name + "</a>" + alumTag(DATA.playerById[o.roster[0]]);
    }
    var extra = [String(o.country || "").split(/\s+(?:Height|Weight|Age|Born)/)[0], o.seed ? "seed " + o.seed : ""].filter(Boolean).join(" · ");
    return name + (extra ? ' <span class="muted small">' + esc(extra) + "</span>" : "") +
      (o.rank ? ' <span class="rk" title="Current ATP singles ranking">ATP #' + esc(o.rank) + "</span>" : "");
  }

  // One row for a player in an event; match may be null (just entered)
  function playerRow(p, ent, hit, showEvent, t) {
    var who = '<div class="row__who">' + playerLink(p) +
      '<div class="row__sub">' + schoolLink(p) + (p.alumni ? " · " + esc(alumLabel(p)) : "") + "</div></div>";
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

  // Numbered rounds ("1st Round", "2nd Round") come before "Round of N": Challenger and ATP draws call the
  // opening round "1st Round" and the next one "Round of 16", Masters events go 1st, 2nd, then Round of 16.
  var ROUND_ORDER = ["1st round", "2nd round", "3rd round", "round of 256", "round of 128", "round of 64", "round of 32", "round of 16",
    "quarter-finals", "quarterfinals", "semi-finals", "semifinals", "final"];
  function roundIdx(m) {
    var r = String(m.round || "").toLowerCase().replace(/^qualifying\s*/, "");
    var i = ROUND_ORDER.indexOf(r);
    return (m.draw === "Qualifying" ? -100 : 0) + (i === -1 ? 50 : i);
  }
  function teamRankOf(id) {
    var p = DATA.playerById[id];
    if (!p) return 9999;
    return p.alumni ? 1000 : parseInt(p.team_rank, 10) || 999;
  }
  function isVs(m) { return !!(m.p1 && m.p2 && m.p1.roster.length && m.p2.roster.length && DATA.playerById[m.p1.roster[0]] && DATA.playerById[m.p2.roster[0]]); }
  // Two college players facing each other: one line, both names the same size
  function vsRow(m, t, showEvent) {
    function side(o, won) {
      var pl = DATA.playerById[o.roster[0]];
      return '<span class="vs__p' + (won ? " vs__w" : "") + '"><span class="vs__line"><a href="#/player/' + esc(pl.id) + '">' + esc(o.name) + "</a>" + rkBadge(pl.id, o.rank) + alumTag(pl) +
        '</span><span class="row__sub">' + schoolLink(pl) + "</span></span>";
    }
    return '<li class="row row--vs"><div class="row__who vs"><span class="round vs__r">' + (showEvent && t ? tournamentLink(t) + " · " : "") +
      esc(m.draw === "Qualifying" ? "Qualifying " : "") + esc(m.round) + (m.live ? ' <span class="wl wl--live">Live</span>' : "") + "</span>" +
      side(m.p1, m.winner === 1) + '<span class="vs__x">vs</span>' + side(m.p2, m.winner === 2) + "</div>" +
      '<div class="result">' + setsHTML(m.sets, false, "") + "</div></li>";
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
  function eventBlock(t, only, all, noHead, mode) {
    mode = mode || "current";
    var ids = [];
    (DATA.entriesByT[t.id] || []).forEach(function (e) { if (ids.indexOf(e.player) < 0) ids.push(e.player); });
    (DATA.matchesByT[t.id] || []).forEach(function (m) {
      ["p1", "p2"].forEach(function (k) { if (m[k]) m[k].roster.forEach(function (pid) { if (ids.indexOf(pid) < 0) ids.push(pid); }); });
    });
    ids = ids.filter(function (id) {
      var pl = DATA.playerById[id];
      return pl && (!only || only[id]) && (mode === "both" || (mode === "alumni") === !!pl.alumni);
    });
    if (!ids.length) return "";
    ids.sort(function (a, b) {
      var A = DATA.playerById[a], B = DATA.playerById[b];
      return (parseInt(A.team_rank, 10) || 99) - (parseInt(B.team_rank, 10) || 99) || A.name.localeCompare(B.name);
    });
    var seen = [];
    function rowFor(pid) {
      var p = DATA.playerById[pid], ent = entryFor(t.id, pid), hits = hitsFor(t.id, pid);
      if (!hits.length) return playerRow(p, ent, null, false, t);
      function one(h) {
        if (seen.indexOf(h.m) >= 0) return "";
        seen.push(h.m);
        return isVs(h.m) ? vsRow(h.m, t, false) : playerRow(p, ent, h, false, t);
      }
      if (all) return hits.map(one).join("");
      var live = hits.filter(function (h) { return h.m.live; })[0];
      return one(live || hits[hits.length - 1]);
    }
    var cur = ids.filter(function (id) { return !DATA.playerById[id].alumni; }), alu = ids.filter(function (id) { return DATA.playerById[id].alumni; });
    var rows = cur.map(rowFor).join("") + (alu.length ? (cur.length ? '<li class="row row--label">Former college tennis players</li>' : "") + alu.map(rowFor).join("") : "");
    if (noHead) return '<section class="event"><ul class="rows">' + rows + "</ul></section>";
    return '<details class="event"' + (t.status === "current" ? " open" : "") + '><summary class="event__head"><h3>' + tournamentLink(t) + "</h3>" + statusTag(t) +
      '<div class="event__meta"><span>' + esc(fmtRange(t.start, t.end)) + "</span><span>" + esc(t.category) + "</span>" +
      (t.country ? "<span>" + esc(t.country) + "</span>" : "") + "<span>" + plural(ids.length, "player") + "</span></div></summary>" +
      '<ul class="rows">' + rows + "</ul></details>";
  }

  function empty(msg) { return '<p class="empty">' + msg + "</p>"; }

  // ---------- pages ----------
  // ---------- last week's recap (the first page) ----------
  // The recap covers the most recent Monday-to-Sunday that has ended. The data updates Sunday night.
  function iso(d) { return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
  function lastWeek() {
    var now = new Date(), back = now.getDay() === 0 ? 7 : now.getDay();
    var end = new Date(now.getFullYear(), now.getMonth(), now.getDate() - back), start = new Date(end.getFullYear(), end.getMonth(), end.getDate() - 6);
    return { start: iso(start), end: iso(end) };
  }
  var LEVEL = { "ATP Tour": 0, "ATP Challenger": 1, "M25": 2, "M15": 3 };
  function levelName(t) { return t.category === "ATP Tour" ? "ATP Tour" : t.category === "ATP Challenger" ? "Challenger" : (t.category || "ITF"); }
  function recapItems(win) {
    var out = { champ: [], final: [], semi: [] };
    DATA.tournaments.filter(function (t) { return t.end >= win.start && t.end <= win.end; }).forEach(function (t) {
      var ms = (DATA.matchesByT[t.id] || []).filter(function (m) { return m.draw === "Main Draw"; });
      var inFinal = {};
      function each(round, fn) {
        ms.filter(function (m) { return String(m.round).toLowerCase().replace(/[\s-]/g, "") === round && m.winner; }).forEach(function (m) {
          [1, 2].forEach(function (side) {
            var me = side === 1 ? m.p1 : m.p2, opp = side === 1 ? m.p2 : m.p1;
            (me.roster || []).forEach(function (id) { if (DATA.playerById[id]) fn(DATA.playerById[id], m, side, opp); });
          });
        });
      }
      each("final", function (pl, m, side, opp) {
        inFinal[pl.id] = true;
        out[m.winner === side ? "champ" : "final"].push({ pl: pl, t: t, m: m, side: side, opp: opp });
      });
      each("semifinals", function (pl, m, side, opp) {
        if (m.winner !== side && !inFinal[pl.id]) out.semi.push({ pl: pl, t: t, m: m, side: side, opp: opp });
      });
    });
    function key(x) { return [LEVEL[x.t.category] === undefined ? 9 : LEVEL[x.t.category], teamRankOf(x.pl.id), x.pl.name]; }
    ["champ", "final", "semi"].forEach(function (k) {
      out[k].sort(function (a, b) { var p = key(a), q = key(b); return p[0] - q[0] || p[1] - q[1] || p[2].localeCompare(q[2]); });
    });
    return out;
  }
  // ---------- newspaper-style headlines ----------
  function scoreText(x) {
    var flip = x.side === 2;
    return (x.m.sets || []).map(function (st) { return (flip ? st[1] : st[0]) + "-" + (flip ? st[0] : st[1]); }).join(", ");
  }
  function oppHTMLShort(o) {
    var rid = o.roster && o.roster.length && DATA.playerById[o.roster[0]];
    return (rid ? '<a href="#/player/' + esc(rid.id) + '">' + esc(o.name) + "</a>" : esc(o.name)) + (o.rank ? ' <span class="muted">(ATP #' + esc(o.rank) + ")</span>" : "");
  }
  function headline(x, kind) {
    var pl = x.pl, who = '<a href="#/player/' + esc(pl.id) + '">' + esc(pl.name) + "</a>", tn = esc(x.t.name);
    if (kind === "champ") return who + " wins " + tn;
    if (kind === "final") return who + " reaches the " + tn + " final";
    return who + " makes the " + tn + " semifinals";
  }
  function oppFull(o) {
    var rid = o && o.roster && o.roster.length && DATA.playerById[o.roster[0]];
    var nm = rid ? '<a href="#/player/' + esc(rid.id) + '">' + esc(o.name) + "</a>" : esc(o.name);
    var extra = rid ? esc(rid.school.replace(/^University of /, "")) : (o.rank ? "ATP #" + esc(o.rank) : "");
    return nm + (extra ? ' <span class="muted">(' + extra + ")</span>" : "");
  }
  function byline(pl) {
    var sch = esc(pl.school.replace(/^University of /, ""));
    return pl.alumni ? "Former " + sch + " player" : sch + (pl.class ? " · " + esc(pl.class) : "");
  }
  function bodyText(x, kind) {
    var opp = x.opp && x.opp.name ? oppFull(x.opp) : "", sc = scoreText(x), rnd = kind === "semi" ? "semifinal" : "final";
    var res = kind === "champ" ? "Beat " : "Lost the " + rnd + " to ";
    if (!opp) return kind === "champ" ? "Won the title." : "Lost in the " + rnd + ".";
    return res + opp + (sc ? ", " + sc : "") + (kind === "champ" ? " in the final." : ".");
  }
  function leadText(x, kind) {
    var pl = x.pl, opp = x.opp && x.opp.name ? oppFull(x.opp) : "", sc = scoreText(x);
    var sch = esc(pl.school.replace(/^University of /, ""));
    var who = pl.alumni ? "The former " + sch + " player" : "The " + sch + (pl.class ? " " + esc(pl.class.toLowerCase()) : " player");
    if (kind === "champ") return who + " beat " + (opp || "the field") + (sc ? " " + sc : "") + " in the final at " + tournamentLink(x.t) + ".";
    return who + " lost the final at " + tournamentLink(x.t) + (opp ? " to " + opp : "") + (sc ? ", " + sc : "") + ".";
  }
  function story(x, kind, big) {
    var pl = x.pl;
    return '<article class="np-story' + (big ? " np-story--lead" : "") + (pl.alumni ? " np-story--alum" : "") + '"><p class="np-tag">' + esc(levelName(x.t)) + " · " + byline(pl) + "</p>" +
      '<h3 class="np-head">' + headline(x, kind) + "</h3>" + '<p class="np-body">' + (big ? leadText(x, kind) : bodyText(x, kind)) + "</p></article>";
  }
  // ---------- extra newspaper sections (all from saved results; nothing is guessed) ----------
  function rankOf(pid) { var r = DATA.ranks[pid]; return r && r.rank ? r.rank : null; }
  function pLink(pl) { return '<a href="#/player/' + esc(pl.id) + '">' + esc(pl.name) + "</a>"; }
  function weekWins(win) {
    var out = [];
    DATA.tournaments.filter(function (t) { return t.end >= win.start && t.end <= win.end; }).forEach(function (t) {
      (DATA.matchesByT[t.id] || []).filter(function (m) { return m.draw === "Main Draw" && m.winner; }).forEach(function (m) {
        var me = m.winner === 1 ? m.p1 : m.p2, opp = m.winner === 1 ? m.p2 : m.p1;
        (me.roster || []).forEach(function (id) { if (DATA.playerById[id]) out.push({ pl: DATA.playerById[id], t: t, m: m, opp: opp }); });
      });
    });
    return out;
  }
  function upsetsHTML(wins) {
    var list = wins.filter(function (w) { return w.opp && w.opp.rank && w.opp.rank <= 500; }).map(function (w) {
      var wr = rankOf(w.pl.id), base = wr || 1500;
      return { w: w, gap: base - w.opp.rank, wr: wr };
    }).filter(function (u) { return u.gap >= 75; }).sort(function (a, b) { return b.gap - a.gap; }).slice(0, 3);
    if (!list.length) return "";
    return '<section class="np-col"><h2 class="np-sec">Upsets of the week</h2>' + list.map(function (u) {
      var w = u.w, sc = scoreText({ m: w.m, side: w.m.winner });
      return '<article class="np-story"><p class="np-tag">' + esc(levelName(w.t)) + '</p><h3 class="np-head">' + pLink(w.pl) + " upsets " + esc(w.opp.name) + ' (ATP #' + w.opp.rank + ')</h3>' +
        '<p class="np-body">' + (u.wr ? "Ranked #" + u.wr : "Unranked") + " (" + esc(w.pl.school.replace(/^University of /, "")) + (w.pl.alumni ? " alum" : "") + "), he won in the " + esc(w.m.round) + " at " + tournamentLink(w.t) + (sc ? ", " + sc : "") + ".</p></article>";
    }).join("") + "</section>";
  }
  function potwHTML(wins, items) {
    var sc = {};
    function add(pl, n, why) { var e = sc[pl.id] || (sc[pl.id] = { pl: pl, pts: 0, wins: 0, best: null, title: null, fin: null }); e.pts += n; return e; }
    wins.forEach(function (w) {
      var e = add(w.pl, 1); e.wins++;
      var r = w.opp && w.opp.rank;
      if (r && r <= 300) { e.pts += r <= 100 ? 2 : 1; if (!e.best || r < e.best.opp.rank) e.best = w; }
    });
    items.champ.forEach(function (x) { var e = add(x.pl, 10); e.title = x.t; });
    items.final.forEach(function (x) { var e = add(x.pl, 5); e.fin = x.t; });
    var all = Object.keys(sc).map(function (k) { return sc[k]; }).sort(function (a, b) { return b.pts - a.pts || b.wins - a.wins; });
    var top = all[0];
    if (!top || top.wins < 2) return "";
    var why = [];
    if (top.title) why.push("won the " + esc(top.title.name) + " title");
    else if (top.fin) why.push("reached the " + esc(top.fin.name) + " final");
    why.push("won " + plural(top.wins, "match", "matches"));
    if (top.best) why.push("including a win over " + esc(top.best.opp.name) + " (ATP #" + top.best.opp.rank + ")");
    return '<section class="np-col np-potw"><h2 class="np-sec">Player of the week</h2><article class="np-story"><h3 class="np-head">' + pLink(top.pl) + '</h3>' +
      '<p class="np-body">' + esc(top.pl.school) + (top.pl.alumni ? " (former player)" : "") + " " + why.join(", ") + ".</p></article></section>";
  }
  function scoreboardHTML(wins) {
    var by = {};
    wins.forEach(function (w) {
      if (w.pl.alumni) return;
      var e = by[w.pl.school] || (by[w.pl.school] = { school: w.pl.school, wins: 0, who: {} });
      e.wins++; e.who[w.pl.id] = 1;
    });
    var rows = Object.keys(by).map(function (k) { return by[k]; }).sort(function (a, b) { return b.wins - a.wins || Object.keys(b.who).length - Object.keys(a.who).length || a.school.localeCompare(b.school); }).slice(0, 5);
    if (!rows.length) return "";
    return '<section class="np-col"><h2 class="np-sec">College scoreboard</h2><p class="np-body">Main-draw match wins by current players. School of the week: <b>' + esc(rows[0].school) + "</b>.</p>" +
      '<table class="np-table"><tbody>' + rows.map(function (r, i) {
        return "<tr><td>" + (i + 1) + '</td><td><a href="#/team/' + esc(slug(r.school)) + '">' + esc(r.school) + "</a></td><td>" + plural(r.wins, "win") + " · " + plural(Object.keys(r.who).length, "player") + "</td></tr>";
      }).join("") + "</tbody></table></section>";
  }
  function moversHTML() {
    var days = Object.keys(DATA.rankHistory || {}).sort(), cutoff = isoDaysAgo(5), base = null;
    days.forEach(function (d) { if (d <= cutoff) base = d; });
    if (!base) return "";
    var snap = DATA.rankHistory[base], moves = [];
    Object.keys(snap).forEach(function (pid) {
      var now = rankOf(pid), pl = DATA.playerById[pid];
      if (pl && now && snap[pid] - now >= 10) moves.push({ pl: pl, from: snap[pid], to: now, up: snap[pid] - now });
    });
    moves.sort(function (a, b) { return b.up - a.up; });
    function block(title, arr) {
      if (!arr.length) return "";
      return "<h3 class=\"np-sub\">" + title + "</h3><ul class=\"np-list\">" + arr.slice(0, 3).map(function (m) {
        return "<li>" + pLink(m.pl) + " <span class=\"muted\">" + esc(m.pl.school) + "</span> · #" + m.from + " → <b>#" + m.to + "</b> (+" + m.up + ")</li>";
      }).join("") + "</ul>";
    }
    var cur = moves.filter(function (m) { return !m.pl.alumni; }), alu = moves.filter(function (m) { return m.pl.alumni; });
    if (!cur.length && !alu.length) return "";
    var d = parts(base);
    return '<section class="np-col"><h2 class="np-sec">Rankings movers</h2><p class="np-body">Biggest ATP ranking climbs since ' + MONTHS[d.m] + " " + d.d + ".</p>" + block("Current players", cur) + block("Former players", alu) + "</section>";
  }
  function weekAheadHTML() {
    var today = iso(new Date()), soon = isoDaysAgo(-7), rows = [];
    DATA.tournaments.filter(function (t) { return t.end >= today && t.start <= soon && (t.status === "current" || t.status === "upcoming"); }).forEach(function (t) {
      var ids = {};
      (DATA.entriesByT[t.id] || []).filter(function (e) { return e.section === "Main Draw" && DATA.playerById[e.player]; }).forEach(function (e) { ids[e.player] = 1; });
      var list = Object.keys(ids).map(function (id) { return DATA.playerById[id]; });
      if (list.length) rows.push({ t: t, list: list });
    });
    rows.sort(function (a, b) { return (LEVEL[a.t.category] || 0) - (LEVEL[b.t.category] || 0) || b.list.length - a.list.length; });
    rows.sort(function (a, b) { return b.list.length - a.list.length; });
    rows = rows.slice(0, 5);
    var vs = DATA.matches.filter(function (m) { var t = DATA.tById[m.tournament]; return t && t.end >= today && !m.winner && m.draw === "Main Draw" && isVs(m); }).slice(0, 4);
    if (!rows.length && !vs.length) return "";
    var h = '<section class="np-col"><h2 class="np-sec">The week ahead</h2>';
    if (rows.length) h += '<ul class="np-list">' + rows.map(function (r) {
      var names = r.list.slice().sort(function (a, b) { return (a.alumni ? 1 : 0) - (b.alumni ? 1 : 0) || (parseInt(a.team_rank, 10) || 99) - (parseInt(b.team_rank, 10) || 99); }).slice(0, 4).map(function (p) { return pLink(p); }).join(", ");
      return "<li>" + tournamentLink(r.t) + ' <span class="muted">(' + esc(levelName(r.t)) + ")</span>: " + plural(r.list.length, "college player") + " in the main draw, including " + names + ".</li>";
    }).join("") + "</ul>";
    if (vs.length) h += '<h3 class="np-sub">College against college</h3><ul class="np-list">' + vs.map(function (m) {
      var a = DATA.playerById[m.p1.roster[0]], b = DATA.playerById[m.p2.roster[0]];
      return "<li>" + pLink(a) + " vs " + pLink(b) + ' <span class="muted">' + esc(m.round) + ", " + tournamentLink(DATA.tById[m.tournament]) + "</span></li>";
    }).join("") + "</ul>";
    return h + "</section>";
  }
  function pageRecap() {
    var win = lastWeek(), items = recapItems(win);
    function d(s) { var p = s.split("-"); return new Date(+p[0], +p[1] - 1, +p[2]).toLocaleDateString(undefined, { month: "long", day: "numeric" }); }
    function split(list, alum) { return list.filter(function (x) { return !!x.pl.alumni === alum; }); }
    var cur = { champ: split(items.champ, false), final: split(items.final, false), semi: split(items.semi, false) },
      alu = { champ: split(items.champ, true), final: split(items.final, true), semi: split(items.semi, true) };
    var html = '<header class="np-mast"><p class="np-mast__top"><span>Weekly edition</span><span>' + d(win.start) + " – " + d(win.end) + "</span></p>" +
      '<h1 class="np-title">College Tennis Headlines</h1><p class="np-mast__sub">Titles and finals won by college players, current and former, at ITF, Challenger and ATP events · ' +
      '<a href="#/week">See this week →</a></p></header>';
    var lead = cur.champ[0] || alu.champ[0] || cur.final[0] || alu.final[0] || null, leadKind = cur.champ[0] || alu.champ[0] ? "champ" : "final";
    function without(list) { return list.filter(function (x) { return x !== lead; }); }
    if (!lead) {
      html += '<p class="empty">No titles or finals from tracked players were saved for ' + d(win.start) + " – " + d(win.end) + ". Results from Sunday's matches appear after the Sunday-night update.</p>";
    } else {
      html += '<section class="np-lead">' + story(lead, leadKind, true) + "</section>";
    }
    function col(title, list, kind) {
      if (!list.length) return "";
      return '<section class="np-col"><h2 class="np-sec">' + title + "</h2>" +
        list.map(function (x) { return story(x, kind, false); }).join("") + "</section>";
    }
    function cols(arr) { return arr.filter(function (c) { return c; }).join(""); }
    var colHtml = cols([
      col("College champions", without(cur.champ), "champ"),
      col("College finalists", without(cur.final), "final"),
      col("Former players: champions", without(alu.champ), "champ"),
      col("Former players: finalists", without(alu.final), "final")]);
    if (colHtml) html += '<div class="np-cols">' + colHtml + "</div>";
    var wins = weekWins(win);
    var extra = potwHTML(wins, items) + upsetsHTML(wins) + moversHTML() + scoreboardHTML(wins) + weekAheadHTML();
    if (extra) html += '<div class="np-cols np-cols--extra">' + extra + "</div>";
    var semi = cur.semi.concat(alu.semi);
    if (semi.length) {
      html += '<details class="np-brief"><summary>In brief: ' + plural(semi.length, "semifinalist") + '</summary><ul>' +
        semi.map(function (x) { return "<li>" + headline(x, "semi") + (x.opp && x.opp.name ? " · lost to " + oppHTMLShort(x.opp) : "") + "</li>"; }).join("") + "</ul></details>";
    }
    app.innerHTML = html;
  }

  function pageHome() {
    var cur = byStatus("current").filter(passes), nxt = byStatus("upcoming").filter(passes),
      past = byStatus("past").filter(isRecent).filter(passes).reverse();
    var tabs = [
      { id: "current", label: "Playing now", list: cur, none: "No roster players are in an event right now. Check Next up for who is entered." },
      { id: "upcoming", label: "Next up", list: nxt, none: "No entry lists are published yet for roster players. Lists usually appear about two weeks before an event." },
      { id: "past", label: "Last two weeks", list: past, none: "No finished events in the last two weeks include roster players." }
    ];
    function hasPlayers(t) { return eventBlock(t, null, false, false, homeView) !== ""; }
    if (!homeTab) homeTab = tabs.filter(function (t) { return t.list.some(hasPlayers); })[0];
    homeTab = homeTab ? tabs.filter(function (t) { return t.id === homeTab.id; })[0] : tabs[0];

    function curCount(t) {
      return new Set((DATA.entriesByT[t.id] || []).map(function (e) { return e.player; }).filter(function (id) { return DATA.playerById[id] && !DATA.playerById[id].alumni; })).size;
    }
    var live = cur.reduce(function (n, t) { return n + curCount(t); }, 0);
    var upc = nxt.reduce(function (n, t) { return n + curCount(t); }, 0);
    var html = '<section class="hero"><h1>Top college players,<br>pro tournaments</h1>' +
      '<p class="lede">Men from the top 30 Division I teams, plus other college players who hold an ATP ranking, at ITF M15 and M25 events, ATP Challengers and the ATP Tour: who is playing now, who is entered next, and how they did.</p>' +
      '<div class="hero__count"><span><b>' + live + "</b>in events now</span><span><b>" + upc + "</b>entered in upcoming events</span><span><b>" +
      DATA.players.length + "</b>players on " + teamList().length + " teams</span></div></section>";
    html += '<div class="chips" role="group" aria-label="Who to show"><button type="button" data-view="current" aria-pressed="' + (homeView === "current") + '">College players</button>' +
      '<button type="button" data-view="alumni" aria-pressed="' + (homeView === "alumni") + '">Former college tennis players</button></div>' +
      filterBar() + '<div class="tabs" role="tablist">' + tabs.map(function (t) {
      return '<button role="tab" data-tab="' + t.id + '" aria-selected="' + (t.id === homeTab.id) + '">' + t.label + "</button>";
    }).join("") + "</div>";
    var blocks = homeTab.list.map(function (t) { return eventBlock(t, null, false, false, homeView); }).join("");
    html += blocks || empty(homeView === "alumni" ? "No alumni in this group of events right now." : homeTab.none);
    app.innerHTML = html;
    bindFilters();
    Array.prototype.forEach.call(app.querySelectorAll("[data-view]"), function (b) {
      b.addEventListener("click", function () { homeView = b.getAttribute("data-view"); pageHome(); });
    });
    Array.prototype.forEach.call(app.querySelectorAll("[data-tab]"), function (b) {
      b.addEventListener("click", function () {
        homeTab = tabs.filter(function (t) { return t.id === b.getAttribute("data-tab"); })[0];
        pageHome();
      });
    });
  }

  function pageTeams() {
    function card(t) {
      var active = t.players.filter(function (p) { return (DATA.entriesByP[p.id] || []).length; }).length;
      return '<li><a href="#/team/' + esc(t.slug) + '"><span><span class="num">' + (t.rank < 999 ? t.rank + " " : "") + "</span><strong>" +
        esc(t.school) + '</strong></span><span class="muted">' + (active ? active + " on tour" : plural(t.players.length, "player")) + "</span></a></li>";
    }
    var all = teamList(), top = all.filter(function (t) { return t.rank < 999; }), more = all.filter(function (t) { return t.rank >= 999; });
    more.sort(function (a, b) { return b.players.length - a.players.length || a.school.localeCompare(b.school); });
    app.innerHTML = "<h1>Teams</h1><p class=\"lede\">The top 30 Division I men's teams by team ranking, plus other schools that have a player with an ATP ranking.</p>" +
      '<div class="section"><h2>Top 30 teams</h2><ul class="grid">' + top.map(card).join("") + "</ul></div>" +
      (more.length ? '<details class="section"><summary><h2>Other schools (' + more.length + ")</h2></summary><ul class=\"grid\">" + more.map(card).join("") + "</ul></details>" : "");
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
      '<div class="section"><h2>Roster</h2><ul class="grid">' + roster + "</ul></div>" +
      '<div class="section"><h2>On tour</h2>' + (blocks || empty("No players from this team are in ITF, Challenger or ATP events in the last two weeks or the next three.")) + "</div>" +
      (DATA.alumniTeams[key] ? '<p class="section"><a href="#/alumni/' + esc(key) + '">' + esc(team.school) + " former college tennis players (" + DATA.alumniTeams[key].players.length + ") →</a></p>" : "");
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
    var html = '<p class="crumbs">' + schoolLink(p) + "</p><h1>" + esc(p.name) + alumTag(p) + "</h1>" +
      '<div class="facts">' + (p.alumni ? "<span><b>" + esc(alumLabel(p)) + "</b></span>" : p.class ? "<span><b>" + esc(p.class) + "</b></span>" : "") +
      (p.hometown ? "<span>" + esc(p.hometown) + "</span>" : "") + (p.colleges ? "<span>College: <b>" + esc(p.colleges) + "</b></span>" : "") + "</div>";
    var rk = DATA.ranks[id];
    if (rk) {
      var bits = [];
      if (rk.rank) bits.push("<span>ATP singles ranking <b>#" + esc(rk.rank) + "</b></span>");
      else if (rk.unranked) bits.push("<span>ATP singles ranking <b>none yet</b></span>");
      if (rk.country) bits.push("<span>" + esc(rk.country) + "</span>");
      if (rk.height) bits.push("<span>Height <b>" + esc(rk.height) + " cm</b></span>");
      if (rk.weight) bits.push("<span>Weight <b>" + esc(rk.weight) + " kg</b></span>");
      if (bits.length) html += '<div class="facts">' + bits.join("") + "</div>";
    }
    html += followButton("p", id);
    if (w + l) html += '<p class="record"><b>' + w + "–" + l + '</b>in singles matches tracked on this site</p>';
    html += '<div class="section"><h2>Coming up</h2>' +
      (upcoming.length ? upcoming.map(function (t) { return eventBlock(t, only, null, false, "both"); }).join("") : empty("Not on any published entry list yet.")) + "</div>";
    html += '<div class="section"><h2>Playing and results</h2>' +
      (played.length ? played.map(function (t) { return eventBlock(t, only, true, false, "both"); }).join("") : empty("No matches tracked yet.")) + "</div>";
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

  // Who is still alive in the main draw, and what round they play next.
  function stillIn(t) {
    var norm = function (r) { return String(r || "").toLowerCase().replace(/[\s-]/g, ""); };
    var mains = (DATA.matchesByT[t.id] || []).filter(function (m) { return m.draw === "Main Draw"; });
    var drawM = (DATA.draws[t.id] || []).filter(function (m) { return m.draw === "Main Draw"; });
    var labels = {}, order = [];
    drawM.concat(mains).forEach(function (m) { if (!labels[norm(m.round)]) { labels[norm(m.round)] = m.round; order.push(m); } });
    var chain = order.slice().sort(function (a, b) { return roundIdx(a) - roundIdx(b); }).map(function (m) { return m.round; });
    [["quarterfinals", "Quarterfinals"], ["semifinals", "Semifinals"], ["final", "Final"]].forEach(function (x) {
      if (chain.length && !labels[x[0]] && chain.every(function (c) { return roundIdx({ round: c, draw: "Main Draw", tournament: t.id }) < roundIdx({ round: x[1], draw: "Main Draw", tournament: t.id }); })) chain.push(x[1]);
    });
    chain.sort(function (a, b) { return roundIdx({ round: a, draw: "Main Draw", tournament: t.id }) - roundIdx({ round: b, draw: "Main Draw", tournament: t.id }); });
    var ids = [];
    (DATA.entriesByT[t.id] || []).forEach(function (e) { if (e.section === "Main Draw" && ids.indexOf(e.player) < 0) ids.push(e.player); });
    mains.forEach(function (m) { [m.p1, m.p2].forEach(function (o) { if (o) o.roster.forEach(function (id) { if (ids.indexOf(id) < 0) ids.push(id); }); }); });
    var inn = [], out = [];
    ids.filter(function (id) { return DATA.playerById[id]; }).forEach(function (id) {
      var mine = mains.filter(function (m) { return [m.p1, m.p2].some(function (o) { return o && o.roster.indexOf(id) >= 0; }); })
        .sort(function (a, b) { return roundIdx(a) - roundIdx(b); });
      var last = mine[mine.length - 1], pl = DATA.playerById[id];
      if (!last) { inn.push({ pl: pl, text: "Waiting to play" + (chain.length ? " " + chain[0] : "") }); return; }
      var side = last.p1 && last.p1.roster.indexOf(id) >= 0 ? 1 : 2;
      if (last.winner === 0) { inn.push({ pl: pl, text: "Playing " + last.round + (last.live ? " (live)" : "") }); return; }
      if (last.winner !== side) { out.push({ pl: pl, text: "Out in " + last.round }); return; }
      var at = chain.findIndex(function (c) { return norm(c) === norm(last.round); });
      if (norm(last.round) === "final") inn.push({ pl: pl, text: "Champion" });
      else inn.push({ pl: pl, text: "Next: " + (at >= 0 && chain[at + 1] ? chain[at + 1] : "next round") });
    });
    if (!inn.length && !out.length) return "";
    function li(x) { return "<li><a href=\"#/player/" + esc(x.pl.id) + "\">" + esc(x.pl.name) + "</a> " + alumTag(x.pl) + '<span class="muted"> ' + esc(x.pl.school) + " · " + esc(x.text) + "</span></li>"; }
    inn.sort(function (a, b) { return teamRankOf(a.pl.id) - teamRankOf(b.pl.id); });
    return '<div class="section"><h2>Still in <span class="muted small">' + inn.length + "</span></h2>" +
      (inn.length ? '<ul class="still">' + inn.map(li).join("") + "</ul>" : empty("No roster players are left in the main draw.")) +
      (out.length ? '<details class="rnd"><summary>Out of the tournament <span class="muted small">' + out.length + '</span></summary><ul class="still">' + out.map(li).join("") + "</ul></details>" : "") + "</div>";
  }

  function roundList(t) {
    var ms = (DATA.matchesByT[t.id] || []).filter(function (m) {
      return [m.p1, m.p2].some(function (o) { return o && o.roster.some(function (id) { return DATA.playerById[id]; }); });
    });
    var groups = [], idx = {};
    ms.slice().sort(function (a, b) { return roundIdx(b) - roundIdx(a); }).forEach(function (m) {
      var k = m.draw + "|" + m.round;
      if (idx[k] === undefined) { idx[k] = groups.length; groups.push({ label: (m.draw === "Qualifying" ? "Qualifying · " : "") + m.round, list: [] }); }
      groups[idx[k]].list.push(m);
    });
    var html = "", seenIn = {};
    groups.forEach(function (g, gi) {
      function best(m) { return Math.min.apply(null, [m.p1, m.p2].filter(Boolean).reduce(function (acc, o) { return acc.concat(o.roster.map(teamRankOf)); }, [9999])); }
      g.list.sort(function (a, b) { return best(a) - best(b); });
      var rows = g.list.map(function (m) {
        if (isVs(m)) return vsRow(m, t, false);
        return [1, 2].map(function (side) {
          var me = side === 1 ? m.p1 : m.p2;
          if (!me || !me.roster.length || !DATA.playerById[me.roster[0]]) return "";
          seenIn[me.roster[0]] = true;
          return playerRow(DATA.playerById[me.roster[0]], null, { m: m, side: side }, false, t);
        }).join("");
      }).join("");
      html += '<details class="rnd"' + (gi === 0 ? " open" : "") + '><summary>' + esc(g.label) + ' <span class="muted small">' + plural(g.list.length, "match", "matches") + '</span></summary><ul class="rows">' + rows + "</ul></details>";
    });
    // entered but no match yet
    var entered = [];
    (DATA.entriesByT[t.id] || []).forEach(function (e) {
      var played = (DATA.matchesByT[t.id] || []).some(function (m) { return [m.p1, m.p2].some(function (o) { return o && o.roster.indexOf(e.player) >= 0; }); });
      if (!played && entered.indexOf(e.player) < 0 && DATA.playerById[e.player]) entered.push(e.player);
    });
    entered.sort(function (a, b) { return teamRankOf(a) - teamRankOf(b); });
    if (entered.length) {
      html += '<details class="rnd"' + (!groups.length ? " open" : "") + '><summary>' + (t.status === "upcoming" ? "Entered" : "Waiting to play") + ' <span class="muted small">' + entered.length + '</span></summary><ul class="rows">' +
        entered.map(function (id) { return playerRow(DATA.playerById[id], entryFor(t.id, id), null, false, t); }).join("") + "</ul></details>";
    }
    return html;
  }

  // The main draw as a real bracket: every round is drawn, rounds not played yet stay empty and fill in as results arrive.
  function bracketHTML(t) {
    var ms = (DATA.draws[t.id] || []).filter(function (m) { return m.draw === "Main Draw"; });
    if (!ms.length) return "";
    var byR = {}, keys = [];
    ms.forEach(function (m, i) {
      m._i = i;
      var k = roundIdx(m);
      if (!byR[k]) { byR[k] = []; keys.push(k); }
      byR[k].push(m);
    });
    keys.sort(function (a, b) { return a - b; });
    var first = byR[keys[0]].length, size = 1;
    var maxSlot = -1;
    ms.forEach(function (m) { [m.p1, m.p2].forEach(function (o) { if (o && o.slot != null && o.slot > maxSlot) maxSlot = o.slot; }); });
    if (maxSlot >= 0) first = Math.max(first, Math.ceil((maxSlot + 1) / 2)); // draws with byes: size comes from the bracket rows
    while (size < first) size *= 2;
    var nRounds = Math.round(Math.log(size) / Math.LN2) + 1;
    function nameOf(d) { // d = rounds from the end
      if (d === 0) return "Final";
      if (d === 1) return "Semi-finals";
      if (d === 2) return "Quarter-finals";
      return "Round of " + Math.pow(2, d + 1);
    }
    function sideKey(o) { // draws sometimes give surname only, so compare on the last word
      if (!o || !o.name) return null;
      var w = plain(o.name).split(" "); return w[w.length - 1];
    }
    function winnerOf(m) { return m ? (m.winner === 1 ? m.p1 : m.winner === 2 ? m.p2 : null) : null; }
    var rounds = [], i, misplaced = 0;
    var ordered = /^m-itf/.test(t.id); // ITF lists matches in draw order; Tennis Explorer lists them in the order they were played
    if (ordered) {
      var r0 = byR[keys[0]].slice().sort(function (a, b) { return a._i - b._i; });
      rounds.push(r0.concat(new Array(size - r0.length).fill(null)));
      for (i = 1; i < nRounds; i++) {
        var slots = new Array(size / Math.pow(2, i)).fill(null);
        var prev = rounds[i - 1], posOf = {};
        prev.forEach(function (m, j) { if (m) [m.p1, m.p2].forEach(function (o) { if (sideKey(o)) posOf[sideKey(o)] = j; }); });
        var real = byR[keys[i]] || [], loose = [];
        real.forEach(function (m) {
          var ps = [sideKey(m.p1), sideKey(m.p2)].map(function (n) { return n in posOf ? posOf[n] : null; }).filter(function (x) { return x !== null; });
          var slot = ps.length ? Math.floor(Math.min.apply(null, ps) / 2) : -1;
          if (slot >= 0 && slot < slots.length && !slots[slot]) slots[slot] = m; else loose.push(m);
        });
        loose.forEach(function (m) { var f = slots.indexOf(null); if (f >= 0) slots[f] = m; });
        rounds.push(slots);
      }
    } else if (ms.every(function (m) { return m.p1 && m.p2 && m.p1.slot != null && m.p2.slot != null; })) {
      // the draw gave every player's first-round position, so each match has an exact place
      for (i = 0; i < nRounds; i++) rounds.push(new Array(size / Math.pow(2, i)).fill(null));
      keys.forEach(function (k, ki) {
        byR[k].slice().sort(function (a, b) { return a._i - b._i; }).forEach(function (m) {
          var j = Math.floor(Math.min(m.p1.slot, m.p2.slot) / Math.pow(2, ki + 1));
          if (rounds[ki] && j < rounds[ki].length && !rounds[ki][j]) rounds[ki][j] = m;
          else if (rounds[ki]) { misplaced++; var f = rounds[ki].indexOf(null); if (f >= 0) rounds[ki][f] = m; }
        });
      });
    } else {
      // build from the latest round back so each match sits next to the match its winner played next
      var top = keys.length - 1;
      for (i = 0; i < nRounds; i++) rounds.push(new Array(size / Math.pow(2, i)).fill(null));
      var topList = byR[keys[top]].slice().sort(function (a, b) { return a._i - b._i; });
      var topIdx = top;
      topList.forEach(function (m, j) { rounds[topIdx][j] = m; });
      for (i = topIdx - 1; i >= 0; i--) {
        var here = rounds[i], up = rounds[i + 1], left = (byR[keys[i]] || []).slice();
        up.forEach(function (um, p) {
          if (!um) return;
          [um.p1, um.p2].forEach(function (o) {
            var k = sideKey(o), n = 0;
            for (n = 0; n < left.length; n++) {
              if (sideKey(left[n].p1) === k || sideKey(left[n].p2) === k) {
                var target = here[2 * p] ? 2 * p + 1 : 2 * p;
                if (!here[target]) { here[target] = left[n]; left.splice(n, 1); }
                break;
              }
            }
          });
        });
        left.forEach(function (m) { var f = here.indexOf(null); if (f >= 0) here[f] = m; });
      }
    }
    function side(o, won, sets, flip) {
      if (o && o.name === "Bye") return '<div class="bk__p bk__p--empty"><span class="bk__n muted">Bye</span><span class="bk__sc"></span></div>';
      if (!o) return '<div class="bk__p bk__p--empty"><span class="bk__n">&nbsp;</span><span class="bk__sc"></span></div>';
      var pl = o.roster && o.roster.length && DATA.playerById[o.roster[0]];
      var cls = pl ? (pl.alumni ? " bk__p--alum" : " bk__p--hl") : "";
      var nm = pl ? '<a href="#/player/' + esc(pl.id) + '">' + esc(o.name) + "</a>" : esc(o.name || "TBD");
      var rk2 = o.rank || (pl && DATA.ranks[pl.id] && DATA.ranks[pl.id].rank);
      return '<div class="bk__p' + (won ? " bk__p--w" : "") + cls + '"><span class="bk__n" title="' + esc(o.name || "") + '">' + (o.seed ? '<span class="bk__seed">' + esc(o.seed) + "</span>" : "") + nm + (o.key ? ' <span class="bk__key">' + esc(o.key) + "</span>" : "") +
        (pl ? ' <span class="dm__s">' + esc(pl.school) + (pl.alumni ? " alumni" : "") + "</span>" : "") +
        (rk2 ? ' <span class="muted small">ATP #' + esc(rk2) + "</span>" : "") + '</span><span class="bk__sc">' +
        (sets || []).map(function (st) { return "<span>" + setCell(flip ? st[1] : st[0]) + "</span>"; }).join("") + "</span></div>";
    }
    var bySlot = {}; // a player who skipped round one (a bye) is only stored in a later round
    ms.forEach(function (m) { [m.p1, m.p2].forEach(function (o) { if (o && o.slot != null && o.name && o.name !== "Bye" && bySlot[o.slot] === undefined) bySlot[o.slot] = o; }); });
    var cols = rounds.map(function (slots, r) {
      var label = nameOf(nRounds - 1 - r);
      return '<div class="bk__col"><h3 class="bk__h">' + esc(label) + '</h3><div class="bk__cards">' + slots.map(function (m, j) {
        var inner;
        if (m) {
          inner = '<div class="bk__card' + (m.live ? " bk__card--live" : "") + '">' + side(m.p1, m.winner === 1, m.sets, false) + side(m.p2, m.winner === 2, m.sets, true) + "</div>";
        } else {
          var a = r > 0 ? winnerOf(rounds[r - 1][2 * j]) : null, b = r > 0 ? winnerOf(rounds[r - 1][2 * j + 1]) : null;
          if (r === 0 && (bySlot[2 * j] || bySlot[2 * j + 1])) { // bye: the seeded player against "Bye"
            a = bySlot[2 * j] || { name: "Bye" }; b = bySlot[2 * j + 1] || { name: "Bye" };
          }
          inner = '<div class="bk__card bk__card--tbd">' + side(a, false, null, false) + side(b, false, null, true) + "</div>";
        }
        return '<div class="bk__slot ' + (j % 2 ? "bk__slot--b" : "bk__slot--a") + (r === nRounds - 1 ? " bk__slot--last" : "") + '">' + inner + "</div>";
      }).join("") + "</div></div>";
    }).join("");
    return '<details class="section" open><summary><h2>Draw</h2></summary><p class="muted"><span class="key key--cur"></span> Current college player <span class="key key--alum"></span> Former player · main draw, later rounds fill in as matches finish. Scroll sideways to see every round.</p>' +
      (misplaced ? '<p class="muted small">Some matches could not be placed exactly in this bracket.</p>' : "") +
      '<div class="bk" style="--n:' + size + '" role="group" aria-label="Main draw bracket">' + cols + "</div></details>";
  }

  function pageTournament(id) {
    var t = DATA.tById[id];
    if (!t) return notFound("tournament");
    var block = roundList(t);
    var still = t.status === "past" ? "" : stillIn(t);
    var html = '<p class="crumbs"><a href="#/tournaments">Tournaments</a></p><h1>' + esc(t.name) + "</h1>" +
      '<div class="facts"><span><b>' + esc(fmtRange(t.start, t.end)) + "</b></span><span>" + esc(t.category) + "</span>" +
      (t.country ? "<span>" + esc(t.country) + "</span>" : "") + "<span>" + statusTag(t) + "</span>" +
      '<span><a href="' + esc(t.url) + '" rel="noopener" target="_blank">' + (/^ATP/.test(t.tour || "") ? "Draws on tennisexplorer.com" : "Draws on itftennis.com") + "</a></span></div>";
    html += still;
    html += '<div class="section">' + (block || empty(t.status === "upcoming"
      ? "No roster players are on the entry list yet. Lists usually appear about two weeks before the event."
      : "No roster players found in this event.")) + "</div>";
    html += bracketHTML(t);
    app.innerHTML = html;
  }

  function alumniTour(a) { return a.players.filter(function (p) { return (DATA.entriesByP[p.id] || []).length; }).length; }
  function pageAlumni() {
    var list = Object.keys(DATA.alumniTeams).map(function (k) { return DATA.alumniTeams[k]; }).sort(function (a, b) {
      var ra = DATA.teams[a.slug] ? DATA.teams[a.slug].rank : 999, rb = DATA.teams[b.slug] ? DATA.teams[b.slug].rank : 999;
      return ra - rb || a.school.localeCompare(b.school);
    });
    function card(a) {
      var n = alumniTour(a);
      return '<li><a href="#/alumni/' + esc(a.slug) + '"><span><strong>' + esc(a.school) + '</strong></span><span class="muted">' +
        (n ? n + " on tour · " : "") + plural(a.players.length, "player") + "</span></a></li>";
    }
    var top = list.filter(function (a) { return DATA.teams[a.slug]; }), more = list.filter(function (a) { return !DATA.teams[a.slug]; });
    more.sort(function (a, b) { return b.players.length - a.players.length || a.school.localeCompare(b.school); });
    app.innerHTML = "<h1>Former college tennis players</h1><p class=\"lede\">Former college players who hold an ATP ranking, grouped by the school they played for last. Kept apart from the current players.</p>" +
      (top.length ? '<div class="section"><h2>Top 30 teams</h2><ul class="grid">' + top.map(card).join("") + "</ul></div>" : "") +
      (more.length ? '<details class="section"><summary><h2>Other schools (' + more.length + ")</h2></summary><ul class=\"grid\">" + more.map(card).join("") + "</ul></details>" : "") +
      (list.length ? "" : empty("No alumni list yet."));
  }
  function pageAlumniTeam(key) {
    var team = DATA.alumniTeams[key];
    if (!team) return notFound("alumni team");
    var only = {};
    team.players.forEach(function (p) { only[p.id] = true; });
    var order = { current: 0, upcoming: 1, past: 2 };
    var events = DATA.tournaments.slice().sort(function (a, b) {
      return order[a.status] - order[b.status] || (a.status === "past" ? b.start.localeCompare(a.start) : a.start.localeCompare(b.start));
    });
    var blocks = events.map(function (t) { return eventBlock(t, only, null, false, "alumni"); }).join("");
    var roster = team.players.slice().sort(function (a, b) {
      var ra = DATA.ranks[a.id] ? DATA.ranks[a.id].rank : 99999, rb = DATA.ranks[b.id] ? DATA.ranks[b.id].rank : 99999;
      return ra - rb || a.name.localeCompare(b.name);
    }).map(function (p) {
      return '<li><a href="#/player/' + esc(p.id) + '"><strong>' + esc(p.name) + rkBadge(p.id) + '</strong><span class="muted">' + esc(alumLabel(p)) + "</span></a></li>";
    }).join("");
    app.innerHTML = '<p class="crumbs"><a href="#/alumni">Former college tennis players</a></p><h1>' + esc(team.school) + " former college tennis players</h1>" +
      '<div class="facts"><span><b>' + team.players.length + "</b> tracked</span>" +
      (DATA.teams[key] ? '<span><a href="#/team/' + esc(key) + '">Current team →</a></span>' : "") + "</div>" +
      '<div class="section"><h2>On tour</h2>' + (blocks || empty("No alumni from this school are in tracked events right now.")) + "</div>" +
      '<div class="section"><h2>Former players</h2><ul class="grid">' + roster + "</ul></div>";
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
      var blocks = list.map(function (t) { return eventBlock(t, only, null, false, "both"); }).join("");
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

  var rankView = "current";
  function pageRanking() {
    var base = rankView === "alumni" ? DATA.alumniAll : DATA.players;
    var list = base.map(function (p) { return { p: p, r: DATA.ranks[p.id] }; })
      .filter(function (x) { return x.r && x.r.rank; })
      .sort(function (a, b) { return a.r.rank - b.r.rank; });
    var html = "<h1>College ranking</h1><p class=\"lede\">Players by current ATP singles ranking. Only players we have seen in Challenger or ATP events so far have a ranking here; more fill in as the season goes.</p>" +
      '<div class="chips"><button type="button" data-rank="current" aria-pressed="' + (rankView === "current") + '">Current players</button>' +
      '<button type="button" data-rank="alumni" aria-pressed="' + (rankView === "alumni") + '">Former college tennis players</button></div>';
    html += list.length ? '<ol class="rank">' + list.map(function (x) {
      return '<li><span class="rank__n">#' + esc(x.r.rank) + '</span><a href="#/player/' + esc(x.p.id) + '"><strong>' + esc(x.p.name) +
        '</strong></a><span class="muted">' + esc(x.p.school) + (x.p.alumni ? " alumni" : "") + "</span></li>";
    }).join("") + "</ol>" : empty("No rankings yet. They appear after the next update.");
    app.innerHTML = html;
    Array.prototype.forEach.call(app.querySelectorAll("[data-rank]"), function (b) {
      b.addEventListener("click", function () { rankView = b.getAttribute("data-rank"); route(true); });
    });
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
    else if (page === "alumni") { if (arg) pageAlumniTeam(arg); else pageAlumni(); }
    else if (page === "ranking") pageRanking();
    else if (page === "week") pageHome();
    else pageRecap();
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
      var pl = DATA.allPlayers.filter(function (p) { return hit(p.name + " " + p.school); }).slice(0, 8);
      var tm = teamList().filter(function (t) { return hit(t.school); }).slice(0, 5);
      var tn = DATA.tournaments.filter(function (t) { return hit(t.name + " " + t.country); }).slice(0, 6);
      var html = "";
      if (pl.length) html += '<li class="group">Players</li>' + pl.map(function (p) {
        return '<li><a href="#/player/' + esc(p.id) + '">' + esc(p.name) + "<small>" + esc(p.school) + (p.alumni ? " alumni" : "") + "</small></a></li>";
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
    .concat([optional("draws.json", {}), optional("rankings.json", {}), optional("rank_history.json", {})]))
    .then(function (r) {
      DATA.players = r[0]; DATA.tournaments = r[1]; DATA.entries = r[2]; DATA.matches = r[3]; DATA.meta = r[4];
      DATA.draws = r[5]; DATA.ranks = r[6]; DATA.rankHistory = (r[7] && r[7].snapshots) || {};
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
