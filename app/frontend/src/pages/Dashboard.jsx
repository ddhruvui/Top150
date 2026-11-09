/* Does this ship? The G-11 verdict first, then the handful of numbers the
   verdict hangs on — each drawn against its own bar (kill / advance / floor),
   so "0.604" reads as "past the kill line, short of advance" at a glance —
   then the evidence: growth, the gate table, member accuracy, baselines,
   robustness and cost sensitivity. */
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { LineChart, BarChart, fmtNum, fmtPct, fmtInt, fmtSignedPct } from '../components/Chart.jsx';
import {
  Card, StatTile, Stats, Badge, Delta, Loading, ErrorBox, useSort, Th, PageHeader,
} from '../components/Bits.jsx';
import Icon from '../components/Icon.jsx';

const EMPTY = [];

const VERDICT = {
  ADVANCE: ['good', 'checkCircle', 'Ready for practice trading',
    'Every quality check passed. The next step is 3–6 months of practice (paper) '
    + 'trading to see how real fills behave — still no real money yet.'],
  ITERATE: ['warn', 'alert', 'Not ready to trade — keep improving',
    'The strategy shows a real signal, but it is not strong enough to pass the '
    + 'ship criteria. The rules say: improve the model, never loosen the bar.'],
  KILL: ['bad', 'xCircle', 'Do not trade — no real edge',
    'Prediction accuracy or the risk-adjusted score is below the minimum. This '
    + 'version of the strategy does not ship.'],
  'LEAKAGE-AUDIT': ['bad', 'alert', 'Too good to be true — check for errors',
    'Results this strong (Sharpe > 2.0 or drawdown < 5%) usually mean the model '
    + 'accidentally peeked at the future. It goes to an error audit, not to trading.'],
};

export default function Dashboard() {
  const [d, setD] = useState({ loading: true });
  const load = () => Promise.all([api.summary(), api.equity().catch(() => null)])
    .then(([summary, equity]) => setD({ summary, equity }))
    .catch((error) => setD({ error }));
  useEffect(() => { load(); }, []);

  const checkSort = useSort(d.summary?.gates?.checks ?? EMPTY);
  const baselineRows = useMemo(() => {
    const b = d.summary?.book || {};
    const bl0 = d.summary?.baselines || {};
    return [
      { name: 'This strategy', color: 'var(--series-1)', strong: true,
        sharpe: b.sharpe_net, ann: b.ann_return, mdd: b.mdd },
      { name: 'SPY buy & hold', color: 'var(--series-2)',
        sharpe: bl0.spy_bh?.sharpe_net, ann: bl0.spy_bh?.ann_return, mdd: bl0.spy_bh?.mdd },
      { name: 'Basic momentum recipe', color: 'var(--series-3)',
        sharpe: bl0.mom_12_1?.sharpe_net, ann: bl0.mom_12_1?.ann_return, mdd: bl0.mom_12_1?.mdd },
    ];
  }, [d.summary]);
  const blSort = useSort(baselineRows);

  if (d.loading) return <Loading what="report" />;
  if (d.error) {
    return (
      <ErrorBox error={d.error} onRetry={() => { setD({ loading: true }); load(); }}
                hint={d.error.body?.hint
                  || 'Nothing published yet — run the pipeline mirror step, which publishes the bundle.'} />
    );
  }

  const { summary, equity } = d;
  const g = summary.gates;
  const book = summary.book || {};
  const bl = summary.baselines || {};
  const [tone, icon, title, blurb] = VERDICT[g.verdict] || VERDICT.ITERATE;
  const passed = (g.checks || []).filter((c) => c.pass).length;
  const total = (g.checks || []).length;

  const eqYears = equity
    && (new Date(equity.end) - new Date(equity.start)) / (365.25 * 86400e3);
  const cagr = equity && eqYears > 0 ? equity.final_equity ** (1 / eqYears) - 1 : null;

  const equitySeries = equity && [{
    name: 'This strategy, after costs',
    color: 'var(--series-1)',
    points: equity.series.map((p) => ({ x: p.date.slice(0, 7), y: p.equity - 1 })),
  }];

  const memberBars = (summary.members || [])
    .filter((m) => m.RankIC != null)
    .map((m) => ({
      label: m.name, value: m.RankIC, tipLabel: 'Rank IC',
      tip: <div className="t-row"><span>Rank ICIR</span><span>{fmtNum(m.RankICIR, 3)}</span></div>,
    }));

  const cpcvBars = (summary.cpcv?.paths || []).map((p) => ({
    label: `Path ${p.path + 1}`, value: p.sharpe, tipLabel: 'Sharpe',
    tip: <div className="t-row"><span>Max drawdown</span><span>{fmtPct(p.mdd)}</span></div>,
  }));

  const sens = Object.entries(summary.sensitivity || {})
    .map(([bps, v]) => ({ label: `${bps} bps`, value: v.sharpe_net, tipLabel: 'Sharpe' }))
    .sort((a, b) => parseInt(a.label, 10) - parseInt(b.label, 10));

  const sharpe = book.sharpe_net;
  const ddAbs = book.mdd == null ? null : Math.abs(book.mdd);
  const ric = summary.ic?.RankIC;

  return (
    <>
      <PageHeader eyebrow="Research · does this ship?" icon="gauge"
                  title="Strategy dashboard"
                  lede="The ship decision (G-11), the numbers it rests on, and the evidence behind them."
                  actions={summary.generated_utc && (
                    <span className="small muted">
                      Report built {summary.generated_utc.replace('T', ' ').replace('+00:00', ' UTC')}
                    </span>
                  )} />

      <section className={`verdict ${tone}`} aria-label="Verdict">
        <div className="ic-wrap"><Icon name={icon} size={22} /></div>
        <div style={{ minWidth: 0 }}>
          <div className="code">{g.verdict}</div>
          <h2>{title}</h2>
          <p>{blurb}</p>
          {total > 0 && (
            <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <Badge kind={passed === total ? 'pass' : 'neutral'} glyph="✓">
                {passed} of {total} checks pass
              </Badge>
              {passed < total && (
                <Badge kind="fail">{total - passed} fail</Badge>
              )}
            </div>
          )}
        </div>
      </section>

      <Stats label="Against the bar">
        <StatTile label="Risk-adjusted score" value={fmtNum(sharpe, 3)}
                  sub="Sharpe · below 0.50 kills it, 0.80 advances"
                  tone={sharpe == null ? '' : sharpe >= 0.5 ? 'pos' : 'neg'}
                  meter={{ value: sharpe, min: 0, max: 1.2,
                    tone: sharpe >= 0.8 ? 'pos' : sharpe >= 0.5 ? 'warn' : 'neg',
                    marks: [{ at: 0.5, label: '0.50' }, { at: 0.8, label: '0.80' }] }} />
        <StatTile label="Worst losing stretch" value={fmtPct(book.mdd)}
                  sub="max drawdown · must stay above −15%" tone="neg"
                  meter={{ value: ddAbs, min: 0, max: Math.max(0.5, (ddAbs || 0) * 1.1),
                    tone: ddAbs != null && ddAbs <= 0.15 ? 'pos' : 'neg',
                    marks: [{ at: 0.15, label: '−15%' }] }} />
        <StatTile label="Prediction accuracy" value={fmtNum(ric, 4)}
                  sub={`rank IC · floor 0.02 · ICIR ${fmtNum(summary.ic?.RankICIR, 2)}`}
                  tone={ric == null ? '' : ric >= 0.02 ? 'pos' : 'neg'}
                  meter={{ value: ric, min: 0, max: Math.max(0.06, (ric || 0) * 1.3),
                    tone: ric >= 0.02 ? 'pos' : 'neg', marks: [{ at: 0.02, label: '0.02' }] }} />
        <StatTile label="Luck-adjusted score" value={fmtNum(book.dsr?.DSR, 3)}
                  sub={`deflated Sharpe over ${fmtInt(book.dsr?.N)} tries`}
                  meter={{ value: book.dsr?.DSR, min: 0, max: 1, marks: [] }} />
      </Stats>
      <Stats label="Returns">
        <StatTile label="Return per year" value={fmtPct(book.ann_return)}
                  sub={`typical yearly swing ±${fmtPct(book.ann_vol)}`}
                  tone={book.ann_return == null ? '' : book.ann_return >= 0 ? 'pos' : 'neg'} />
        <StatTile label="Growth per year" value={fmtSignedPct(cagr, 1)}
                  sub={eqYears ? `compound, over ${fmtNum(eqYears, 1)} years` : ''}
                  tone={cagr == null ? '' : cagr >= 0 ? 'pos' : 'neg'} />
        <StatTile label="Trades tested" value={fmtInt(book.n_trades)}
                  sub={`held ${fmtNum(book.avg_hold_sessions, 1)} trading days on average`} />
      </Stats>

      {equitySeries && (
        <Card title="How money in this strategy would have grown"
              subtitle={`Simulated from ${equity.start} to ${equity.end}, after trading costs. `
                + `Total ${fmtSignedPct(equity.final_equity - 1, 1)} · average ${fmtSignedPct(cagr, 1)} per year `
                + `· worst losing stretch ${fmtPct(equity.max_drawdown)}.`}>
          <LineChart series={equitySeries} height={300} zeroLine
                     label="Cumulative return of the strategy after costs"
                     yFormat={(v) => fmtSignedPct(v, 0)} />
        </Card>
      )}

      <Card flush title="Quality checks (the G-11 gates)"
            subtitle="Every rule the strategy must pass before it counts as tradeable. One fail and it stays in research."
            right={total > 0 && <Badge kind={passed === total ? 'pass' : 'neutral'}>{passed} / {total} pass</Badge>}>
        <div className="table-wrap">
          <table className="sticky-first">
            <thead>
              <tr>
                <Th k="id" sort={checkSort.sort} onSort={checkSort.onSort}>Check</Th>
                <Th k="value" num sort={checkSort.sort} onSort={checkSort.onSort}>This strategy</Th>
                <Th k="threshold" num sort={checkSort.sort} onSort={checkSort.onSort}>Needs to be</Th>
                <Th k="pass" sort={checkSort.sort} onSort={checkSort.onSort}>Result</Th>
                <Th>What it means</Th>
              </tr>
            </thead>
            <tbody>
              {checkSort.rows.map((c) => (
                <tr key={c.id}>
                  <td className="strong">{c.id}</td>
                  <td className="n">{fmtNum(c.value, 4)}</td>
                  <td className="n muted">{c.op} {fmtNum(c.threshold, 4)}</td>
                  <td><Badge kind={c.pass ? 'pass' : 'fail'}>{c.pass ? 'Pass' : 'Fail'}</Badge></td>
                  <td className="muted small">{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid cols-2">
        <Card title="How accurate is each model?"
              subtitle="The strategy blends several models. Each bar is one model's prediction accuracy (rank IC) on data it never saw; a model gets a vote only above the 0.02 floor.">
          <BarChart data={memberBars} horizontal height={Math.max(180, memberBars.length * 30 + 40)}
                    refLine={summary.member_admission_floor} refLabel="0.02 floor"
                    label="Rank IC by model" valueFormat={(v) => fmtNum(v, 3)} />
        </Card>

        <Card flush title="Does it beat doing the simple thing?"
              subtitle="If the strategy can't beat just buying the index (SPY) and a basic momentum recipe, it doesn't ship.">
          <div className="table-wrap">
            <table>
              <thead><tr>
                <Th k="name" sort={blSort.sort} onSort={blSort.onSort}>Approach</Th>
                <Th k="sharpe" num sort={blSort.sort} onSort={blSort.onSort}>Risk-adjusted score</Th>
                <Th k="ann" num sort={blSort.sort} onSort={blSort.onSort}>Return per year</Th>
                <Th k="mdd" num sort={blSort.sort} onSort={blSort.onSort}>Worst stretch</Th>
              </tr></thead>
              <tbody>
                {blSort.rows.map((r) => (
                  <tr key={r.name}>
                    <td className={r.strong ? 'strong' : ''}>
                      <span className="swatch sq" style={{ background: r.color }} aria-hidden="true" />{r.name}
                    </td>
                    <td className="n">{r.strong ? <strong>{fmtNum(r.sharpe, 3)}</strong> : fmtNum(r.sharpe, 3)}</td>
                    <td className="n">{fmtPct(r.ann)}</td>
                    <td className="n">{fmtPct(r.mdd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card-body">
            <div className="note">
              Extra return beyond what the market itself gave (alpha):{' '}
              <Delta value={bl.alpha_beta_vs_spy?.alpha_ann} /> per year · moves{' '}
              {fmtNum(bl.alpha_beta_vs_spy?.beta, 2)}× as much as the market (beta).
            </div>
          </div>
        </Card>
      </div>

      <div className="grid cols-2">
        {cpcvBars.length > 0 && (
          <Card title="Stability check"
                subtitle={`The same strategy re-scored on 5 alternate re-shuffles of history (CPCV). Similar bars = the result isn't a fluke of one particular period. Median score ${fmtNum(summary.cpcv.sharpe_median, 2)}, worst losing stretch across paths ${fmtPct(summary.cpcv.mdd_worst)}. A robustness estimate, not a live-tradeable number.`}>
            <BarChart data={cpcvBars} height={220} label="Sharpe by CPCV path"
                      valueFormat={(v) => fmtNum(v, 2)} />
          </Card>
        )}
        {sens.length > 0 && (
          <Card title="What if trading got more expensive?"
                subtitle="The risk-adjusted score as per-trade costs rise (5, 15, 30 hundredths of a percent). Shows how much of the edge survives real-world fees and slippage.">
            <BarChart data={sens} height={220} bySign label="Sharpe by per-trade cost"
                      valueFormat={(v) => fmtNum(v, 2)} />
          </Card>
        )}
      </div>

      <Card title="Provenance" right={<Icon name="database" size={16} className="muted" />}>
        <dl className="dl">
          <dt>Universe</dt>
          <dd>{fmtInt(summary.universe?.names)} names ever in-scope, {fmtNum(summary.universe?.avg_daily, 0)} per day (survivorship-free).</dd>
          <dt>Config hash</dt><dd><code>{String(summary.stamp?.config_hash || '').slice(0, 12)}</code></dd>
          <dt>Data snapshot</dt><dd><code>{summary.stamp?.data_snapshot_id}</code></dd>
          <dt>Git</dt><dd><code>{String(summary.stamp?.git_sha || '').slice(0, 8)}</code> · seed {summary.stamp?.seed}</dd>
          <dt>Caveat</dt><dd>{summary.caveat}</dd>
        </dl>
      </Card>
    </>
  );
}
