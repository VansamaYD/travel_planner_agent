import js from '@eslint/js'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'coverage'] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['**/features/*/**/internal/**'],
              message: 'Import a feature through its public entry point.',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['eslint.config.js'],
    rules: {
      '@typescript-eslint/no-unsafe-assignment': 'off',
    },
  },
)
