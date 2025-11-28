# DNR-Theming-Spec-v1

## Project: Dazzle Native Runtimes (DNR)
### Topic: Theming, Design Tokens, and Framework-Agnostic Skinning

This document defines the theming architecture for DNR-UI, supporting semantic styling, design tokens, and pluggable CSS skins for Tailwind, Bootstrap, and custom CSS.

---

# 1. Purpose

The theming system must:

- Maintain **token efficiency** for LLM-first spec generation.
- Keep stylistic concerns **out of UISpec**, mapping semantics → concrete styling via skins.
- Produce **performant, attractive** output for web/mobile.
- Support multiple skins without changing the core UISpec.
- Make design portable across web, iOS, Android, and desktop.

---

# 2. Design Tokens

Design tokens express atomic style values.

## 2.1 Token Types

```ts
type ColorToken =
  | "background" | "surface" | "surfaceAlt"
  | "textPrimary" | "textSecondary" | "textInverse"
  | "primary" | "primaryHover" | "primaryActive"
  | "danger" | "dangerHover"
  | "success" | "info" | "warning";

type SpaceToken = "xxs" | "xs" | "sm" | "md" | "lg" | "xl" | "xxl";

type RadiusToken = "none" | "sm" | "md" | "lg" | "full";

type TypographyToken =
  | "body" | "bodyStrong" | "subtle"
  | "headingSm" | "headingMd" | "headingLg";

type ShadowToken = "none" | "sm" | "md" | "lg";

type BorderToken = "none" | "thin" | "medium" | "thick";
```

## 2.2 ThemeSpec

```ts
type ThemeSpec = {
  colors: Record<ColorToken, string>;
  spacing: Record<SpaceToken, string>;
  radius: Record<RadiusToken, string>;
  typography: Record<TypographyToken, {
    fontSize: string;
    fontWeight: string;
    lineHeight?: string;
  }>;
  shadows: Record<ShadowToken, string>;
  borders: Record<BorderToken, string>;
  metadata?: Record<string, any>;
};
```

---

# 3. Component Variants

Components use semantic options instead of raw styles or classes.

## 3.1 Variant Definitions

```ts
type Variant =
  | "primary" | "secondary" | "tertiary"
  | "ghost" | "danger" | "success"
  | "info" | "warning";
```

## 3.2 Sizes

```ts
type SizeVariant = "xs" | "sm" | "md" | "lg" | "xl";
```

## 3.3 Density

```ts
type Density = "compact" | "comfortable" | "spacious";
```

## 3.4 UISpec Example

```json
{
  "kind": "element",
  "as": "Button",
  "props": {
    "variant": "primary",
    "size": "md",
    "density": "comfortable"
  },
  "children": [{ "kind": "text", "value": "Submit" }]
}
```

---

# 4. Layout Semantics

The DSL defines layout roles without CSS leaking in.

```ts
type LayoutKind =
  | "row" | "column" | "stack"
  | "gridTwo" | "gridThree" | "gridFour"
  | "sidebar" | "hero" | "navbar" | "footer";
```

Example:

```json
{
  "kind": "layout",
  "layoutKind": "gridThree",
  "gap": "md",
  "align": "start",
  "children": [...]
}
```

---

# 5. Runtime Responsibilities

The DNR-UI runtime must:

1. Load UISpec + ThemeSpec.
2. Translate semantic variants → resolved styles.
3. Delegate final CSS generation to a chosen skin.

---

# 6. Skin Architecture

A **skin** is a pluggable mapping from DNR semantics → concrete styling rules.

## 6.1 Skin Interface

```ts
type Skin = {
  name: string;
  mapComponentVariant: (
    componentName: string,
    variant: Variant,
    size: SizeVariant,
    density: Density
  ) => ResolvedWebStyles;

  mapLayout: (layoutKind: LayoutKind, gap: SpaceToken) => ResolvedWebStyles;

  mapTokens: (theme: ThemeSpec) => CSSVariableMap;
};
```

## 6.2 Resolved Styles

```ts
type ResolvedWebStyles =
  | { kind: "cssClassList"; classes: string[] }
  | { kind: "inlineStyles"; styles: Record<string, string> }
  | { kind: "cssModuleRef"; moduleName: string; className: string };
```

---

# 7. Example Skins

## 7.1 Tailwind Skin

```ts
TailwindSkin.mapComponentVariant("Button", "primary", "md", "comfortable") =>
{
  kind: "cssClassList",
  classes: [
    "inline-flex", "items-center", "justify-center",
    "px-4", "py-2",
    "rounded-md",
    "text-white",
    "bg-indigo-600",
    "hover:bg-indigo-700",
    "shadow-sm"
  ]
}
```

## 7.2 Bootstrap Skin

```ts
BootstrapSkin.mapComponentVariant("Button", "primary", "md", "comfortable") =>
{
  kind: "cssClassList",
  classes: ["btn", "btn-primary", "btn-md"]
}
```

## 7.3 Custom Skin

```ts
CustomSkin.mapComponentVariant("Button", "primary", "md") =>
{
  kind: "cssClassList",
  classes: ["dnr-btn-primary-md"]
}
```

---

# 8. Cross-Platform Mapping

## 8.1 iOS (SwiftUI)

```swift
Button("Save") { /* action */ }
  .buttonStyle(PrimaryButtonStyle(size: .medium, density: .comfortable))
```

## 8.2 Android (Jetpack Compose)

```kotlin
PrimaryButton(
  text = "Save",
  size = Size.Medium,
  density = Density.Comfortable
)
```

---

# 9. Theme Inheritance & Overrides

Partial overrides are allowed:

```json
{
  "theme": {
    "colors": {
      "primary": "#0ea5e9"
    },
    "radius": {
      "md": "10px"
    }
  }
}
```

---

# 10. Validation Rules

- All variant values must be valid enumerations.
- All tokens referenced must exist in ThemeSpec.
- Layout kinds must be supported by the skin.
- UISpec must not contain raw CSS or classes.

---

# 11. Summary

DNR-Theming provides:

- Semantic, portable styling.
- Design tokens for consistency.
- Variant-based components.
- Layout primitives.
- Web skins for Tailwind/Bootstrap/custom CSS.
- Native runtime mapping for iOS/Android.

Human authors and LLMs work with tokens and variants; skins handle presentation.

End of DNR-Theming-Spec-v1.
