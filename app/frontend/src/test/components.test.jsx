import { describe, expect, it, vi } from 'vitest';
import { render, screen, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import {
  useSort, Th, Delta, Badge, Callout, ConfirmButton, Drawer, Segmented, Meter, StatTile,
  EmptyState, ErrorBox, Loading,
} from '../components/Bits.jsx';
import { LineChart, BarChart } from '../components/Chart.jsx';
import { ToastProvider, useToast } from '../components/Toast.jsx';

function SortTable({ rows }) {
  const s = useSort(rows);
  return (
    <table>
      <thead><tr>
        <Th k="name" sort={s.sort} onSort={s.onSort}>Name</Th>
        <Th k="v" num sort={s.sort} onSort={s.onSort}>Value</Th>
        <Th>Notes</Th>
      </tr></thead>
      <tbody>{s.rows.map((r) => <tr key={r.name}><td>{r.name}</td><td>{r.v}</td><td /></tr>)}</tbody>
    </table>
  );
}
const names = () => screen.getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[0].textContent);

describe('sortable tables', () => {
  const rows = [{ name: 'b', v: 2 }, { name: 'a', v: null }, { name: 'c', v: 3 }];

  it('cycles desc → asc → original order and keeps nulls last', async () => {
    const user = userEvent.setup();
    render(<SortTable rows={rows} />);
    const btn = screen.getByRole('button', { name: /value/i });
    const th = btn.closest('th');
    expect(th).toHaveAttribute('aria-sort', 'none');

    await user.click(btn);
    expect(th).toHaveAttribute('aria-sort', 'descending');
    expect(names()).toEqual(['c', 'b', 'a']);

    await user.click(btn);
    expect(th).toHaveAttribute('aria-sort', 'ascending');
    expect(names()).toEqual(['b', 'c', 'a']);

    await user.click(btn);
    expect(th).toHaveAttribute('aria-sort', 'none');
    expect(names()).toEqual(['b', 'a', 'c']);
  });

  it('sorts from the keyboard, and plain headers are not buttons', async () => {
    const user = userEvent.setup();
    render(<SortTable rows={rows} />);
    await user.tab();
    expect(screen.getByRole('button', { name: /name/i })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(names()).toEqual(['c', 'b', 'a']);
    expect(screen.queryByRole('button', { name: /notes/i })).toBeNull();
    expect(screen.getByRole('columnheader', { name: 'Notes' })).toBeInTheDocument();
  });
});

describe('profit / loss primitives', () => {
  it('Delta pairs colour with a sign and a glyph', () => {
    const { container, rerender } = render(<Delta value={0.0405} />);
    expect(container.textContent).toBe('▲ +4.05%');
    expect(container.firstChild).toHaveClass('pos');
    rerender(<Delta value={-0.1083} />);
    expect(container.textContent).toBe('▼ -10.83%');
    expect(container.firstChild).toHaveClass('neg');
    rerender(<Delta value={null} />);
    expect(container.textContent).toBe('—');
  });

  it('Badge shows a pass/fail glyph so status is not colour-only', () => {
    render(<><Badge kind="pass">Pass</Badge><Badge kind="fail">Fail</Badge></>);
    expect(screen.getByText('Pass').textContent).toBe('✓Pass');
    expect(screen.getByText('Fail').textContent).toBe('✕Fail');
  });

  it('StatTile renders a threshold meter with labelled marks', () => {
    const { container } = render(
      <StatTile label="Risk-adjusted score" value="0.604"
                meter={{ value: 0.604, min: 0, max: 1.2, marks: [{ at: 0.5, label: '0.50' }, { at: 0.8, label: '0.80' }] }} />,
    );
    expect(screen.getByText('Risk-adjusted score')).toBeInTheDocument();
    const fill = container.querySelector('.meter .fill');
    expect(fill.style.width).toMatch(/^50\.3/);
    expect(screen.getByText('0.80')).toBeInTheDocument();
  });

  it('Meter renders nothing without a value', () => {
    const { container } = render(<Meter value={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('callouts', () => {
  it('keeps secondary copy one click away instead of dropping it', async () => {
    const user = userEvent.setup();
    render(<Callout tone="warning" title="Practice money only" detail="Use the paper book.">Not ready.</Callout>);
    expect(screen.queryByText('Use the paper book.')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'More' }));
    expect(screen.getByText('Use the paper book.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'More' })).toBeNull();
  });
});

describe('ConfirmButton', () => {
  it('needs two clicks before it acts', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<ConfirmButton onConfirm={onConfirm} confirmText="Cancel order?">Cancel</ConfirmButton>);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onConfirm).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Cancel order?' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('disarms itself after a few seconds', () => {
    vi.useFakeTimers();
    try {
      render(<ConfirmButton onConfirm={() => {}}>Cancel</ConfirmButton>);
      act(() => { screen.getByRole('button').click(); });
      expect(screen.getByRole('button')).toHaveTextContent('Confirm?');
      act(() => { vi.advanceTimersByTime(4100); });
      expect(screen.getByRole('button')).toHaveTextContent('Cancel');
    } finally { vi.useRealTimers(); }
  });
});

describe('Drawer', () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>Open AMD</button>
        <Drawer open={open} onClose={() => setOpen(false)} title="AMD detail" subtitle="since 2007">
          <p>chart here</p>
        </Drawer>
      </>
    );
  }

  it('opens as a modal dialog, closes on Esc, and hands focus back', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Open AMD' });
    await user.click(opener);
    const dialog = screen.getByRole('dialog', { name: 'AMD detail' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveFocus();
    expect(document.body.style.overflow).toBe('hidden');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
    expect(document.body.style.overflow).toBe('');
  });

  it('closes from its close button', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('button', { name: 'Open AMD' }));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('Segmented', () => {
  it('marks exactly one option pressed and reports changes', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Segmented label="View" value="a" onChange={onChange} options={[['a', 'Simple'], ['b', 'Detailed']]} />);
    expect(screen.getByRole('group', { name: 'View' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Simple' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Detailed' })).toHaveAttribute('aria-pressed', 'false');
    await user.click(screen.getByRole('button', { name: 'Detailed' }));
    expect(onChange).toHaveBeenCalledWith('b');
  });
});

describe('toasts', () => {
  function Fire() {
    const toast = useToast();
    return <button type="button" onClick={() => toast({ ok: false, text: 'BA: rejected' })}>fire</button>;
  }
  it('announces results in a live region and can be dismissed', async () => {
    const user = userEvent.setup();
    render(<ToastProvider><Fire /></ToastProvider>);
    await user.click(screen.getByRole('button', { name: 'fire' }));
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(within(region).getByText('BA: rejected')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByText('BA: rejected')).toBeNull();
  });
});

describe('feedback states', () => {
  it('Loading announces itself to assistive tech', () => {
    render(<Loading what="report" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading report…');
  });

  it('ErrorBox shows the message, the hint and a retry', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorBox error={new Error('summary not published yet')} hint="publish the bundle" onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('summary not published yet');
    expect(screen.getByText('publish the bundle')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });

  it('EmptyState explains what to do', () => {
    render(<EmptyState title="No finished trades yet">Track one first.</EmptyState>);
    expect(screen.getByText('No finished trades yet')).toBeInTheDocument();
  });
});

describe('charts', () => {
  it('LineChart draws one path per series, labelled for screen readers', () => {
    const series = [
      { name: 'Book', color: 'red', points: [{ x: '2020', y: 1 }, { x: '2021', y: 2 }, { x: '2022', y: 1.5 }] },
      { name: 'SPY', color: 'blue', points: [{ x: '2020', y: 1 }, { x: '2021', y: 1.2 }, { x: '2022', y: 1.4 }] },
    ];
    render(<LineChart series={series} label="Growth" />);
    const svg = screen.getByRole('img', { name: 'Growth' });
    expect(svg.querySelectorAll('path[stroke="red"]')).toHaveLength(1);
    expect(screen.getByText('Book')).toBeInTheDocument();
    expect(screen.getByText('SPY')).toBeInTheDocument();
  });

  it('LineChart log axis uses round 1-2-5 ticks', () => {
    const pts = [250000, 1e6, 6.3e6].map((y, i) => ({ x: String(i), y }));
    render(<LineChart series={[{ name: 'Pots', color: 'red', points: pts }]} logY
                      tickFormat={(v) => `t${v}`} label="log" />);
    const ticks = [...screen.getByRole('img').querySelectorAll('text')]
      .map((t) => t.textContent).filter((t) => t.startsWith('t'));
    expect(ticks).toEqual(expect.arrayContaining(['t1000000']));
    for (const t of ticks) {
      const lead = Number(t.slice(1)) / 10 ** Math.floor(Math.log10(Number(t.slice(1))));
      expect([1, 2, 5]).toContain(Math.round(lead));
    }
  });

  it('BarChart draws a bar per datum and handles empty data', () => {
    const data = [{ label: 'D1', value: 0.01 }, { label: 'D2', value: -0.02 }];
    const { rerender } = render(<BarChart data={data} bySign label="Deciles" />);
    const svg = screen.getByRole('img', { name: 'Deciles' });
    expect(svg.querySelector('path[fill="var(--profit)"]')).not.toBeNull();
    expect(svg.querySelector('path[fill="var(--loss)"]')).not.toBeNull();
    rerender(<BarChart data={[]} />);
    expect(screen.getByText('No data')).toBeInTheDocument();
  });

  it('horizontal BarChart draws its reference line label', () => {
    render(<BarChart horizontal data={[{ label: 'lgbm_h20', value: 0.055 }]} refLine={0.02}
                     refLabel="0.02 floor" label="IC" />);
    expect(screen.getByText('0.02 floor')).toBeInTheDocument();
    expect(screen.getByText('lgbm_h20')).toBeInTheDocument();
  });
});
