import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Skeleton } from '../Skeleton';
import React from 'react';

/**
 * @test Skeleton component
 */
describe('Skeleton', () => {
  /**
   * Ensures default skeleton class is applied.
   */
  it('renders with default skeleton class', () => {
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toBeDefined();
    const element = container.firstChild as HTMLElement;
    expect(element.className).toContain('skeleton');
  });
});
