import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import globals from 'globals';

export default tseslint.config(
  {
    // demo/ is a separate Python-based scenario engine (its own venv/vendored JS
    // deps live under demo/.venv, not part of this package's linted surface).
    ignores: ['dist/**', 'node_modules/**', 'playwright-report/**', 'test-results/**', 'demo/**'],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      '@typescript-eslint/ban-ts-comment': 'off',
    },
  },
  {
    // CJS/plain-JS helper scripts (patch_*.cjs, scripts/*.cjs) run under Node, not
    // the browser -- they need Node globals and require() is expected, not banned.
    files: ['**/*.{mjs,cjs,js}'],
    languageOptions: { globals: globals.node },
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
);
