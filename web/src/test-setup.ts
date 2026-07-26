/**
 * jsdom does not implement scrollIntoView.
 *
 * Stubbed here rather than guarded in the component: it exists in every real
 * browser, so a runtime check would be dead code shaped like caution.
 */
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
