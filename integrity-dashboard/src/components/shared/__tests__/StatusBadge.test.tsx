import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../StatusBadge';
import React from 'react';

/**
 * @test StatusBadge component
 */
describe('StatusBadge', () => {
  /**
   * Validates badge class for active status.
   */
  it('renders success badge for active status', () => {
    render(<StatusBadge status="Active" />);
    const badge = screen.getByText('Active');
    expect(badge.className).toContain('badge-aa');
  });

  /**
   * Validates tier calculation from AIS score.
   */
  it('renders tier based on AIS', () => {
    render(<StatusBadge ais={950} />);
    // In our implementation, 950 maps to AAA
    expect(screen.getByText(/AAA/)).toBeDefined();
  });
});
