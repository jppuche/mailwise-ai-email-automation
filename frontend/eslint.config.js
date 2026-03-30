import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'src/types/generated']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Directiva D4 (tighten-types): no explicit any
      '@typescript-eslint/no-explicit-any': 'error',
      // Context files and router mix components + hooks/constants — standard React pattern.
      // Downgrade to warn (not error) to avoid false positives on Provider+hook co-location.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
])
