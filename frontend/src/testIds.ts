/**
 * Every data-testid in the app. E2E tests select by role, accessible name or one of these IDs,
 * never by CSS classes (QA-05). The table in README.md is checked against this object.
 */
export const testIds = {
  tabLists: 'tab-lists',
  tabMeals: 'tab-meals',
  tabIngredients: 'tab-ingredients',
  tabMe: 'tab-me',
  screenLists: 'screen-lists',
  screenMeals: 'screen-meals',
  screenIngredients: 'screen-ingredients',
  screenMe: 'screen-me',
  languageSelect: 'language-select',
  appVersion: 'app-version',
  sourceLink: 'source-link',
  updatePrompt: 'update-prompt',
} as const;

export type TestId = (typeof testIds)[keyof typeof testIds];
