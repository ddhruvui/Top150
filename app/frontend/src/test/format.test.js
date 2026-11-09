import { describe, expect, it } from 'vitest';
import {
  fmtPct, fmtSignedPct, fmtNum, fmtInt, fmtMoneyShort, arrow, signClass,
} from '../components/Chart.jsx';
import { describeBuilt } from '../App.jsx';
import { pretty } from '../pages/Today.jsx';

describe('number formatting', () => {
  it('formats percentages, with and without sign', () => {
    expect(fmtPct(0.0823)).toBe('8.2%');
    expect(fmtPct(0.0823, 2)).toBe('8.23%');
    expect(fmtSignedPct(0.107)).toBe('+10.7%');
    expect(fmtSignedPct(-0.435)).toBe('-43.5%');
    expect(fmtSignedPct(0)).toBe('+0.0%');
  });

  it('renders a dash for missing values instead of NaN', () => {
    for (const f of [fmtPct, fmtSignedPct, fmtNum, fmtInt, fmtMoneyShort]) {
      expect(f(null)).toBe('—');
      expect(f(undefined)).toBe('—');
      expect(f(Number.NaN)).toBe('—');
    }
  });

  it('groups integers the US way', () => {
    expect(fmtInt(10475)).toBe('10,475');
    expect(fmtNum(0.60414702, 3)).toBe('0.604');
  });

  it('abbreviates money for axis ticks', () => {
    expect(fmtMoneyShort(500000)).toBe('$500K');
    expect(fmtMoneyShort(1000000)).toBe('$1M');
    expect(fmtMoneyShort(6375780)).toBe('$6.4M');
    expect(fmtMoneyShort(-2500)).toBe('−$3K');
    expect(fmtMoneyShort(250)).toBe('$250');
  });

  it('carries profit/loss in a glyph and a class, never colour alone', () => {
    expect(arrow(0.1)).toBe('▲');
    expect(arrow(-0.1)).toBe('▼');
    expect(arrow(null)).toBe('');
    expect(signClass(0.1)).toBe('pos');
    expect(signClass(-0.1)).toBe('neg');
  });
});

describe('dates', () => {
  it('names the trading day in plain words', () => {
    expect(pretty('2026-11-09')).toBe('Monday 9 Nov');
    expect(pretty('2026-10-01')).toBe('Thursday 1 Oct');
    expect(pretty(null)).toBe('—');
  });

  it('describes how old the published report is', () => {
    const now = new Date('2026-11-09T12:00:00Z');
    const b = describeBuilt('2026-10-02T14:10:08+00:00', now);
    expect(b.when).toBe('2 Oct 2026, 14:10 UTC');
    expect(b.age).toBe('37 days ago');
    expect(describeBuilt('2026-11-09T01:00:00Z', now).age).toBe('today');
    expect(describeBuilt('2026-11-08T01:00:00Z', now).age).toBe('yesterday');
    expect(describeBuilt(null)).toBeNull();
    expect(describeBuilt('not a date')).toBeNull();
  });
});
