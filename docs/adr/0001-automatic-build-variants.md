---
status: accepted
---

# Automatic build variants for build-time parameters

Run settings may set any model parameter, and sweeps reuse cached builds wherever possible. Most parameters can be changed in a run, so a sweep over them runs one cached build at every point. When OMC has fixed a requested parameter while translating the model (an array size, a Boolean selecting an if-equation, `Evaluate=true`), mtools builds a variant with that value fixed and caches it like any other build. A sweep therefore needs one build per distinct combination of build-time values, and every other parameter varies per run. For example, sweeping `k` over 10 values and `n` over 3 makes 3 builds and 30 runs, and running the sweep again builds nothing. We chose this so that users never need to know which parameters OMC fixes; that depends on how a parameter is used in the model and can change when the model changes.

## Considered Options

- **An explicit `build.parameters` field**, with `ConfigError` for a build-time parameter given in `settings.parameters`. It makes the build cost visible in the config, but users would have to move parameters between config groups whenever the model changes. Rejected.

## Consequences

- The first sweep over a build-time parameter costs one compile per distinct value. mtools logs at INFO which parameters caused a variant.
- The plain build is always made first, because its `_init.xml` is what tells which requested parameters are fixed.
- A variant is a generated wrapper class, `model <variant> extends <model>(<build-time modifiers>)`, so the user's model is never edited and inherited parameters work. OMC's `setComponentModifierValue` was rejected because it silently fails on inherited parameters.
- A `final` parameter cannot be changed even in a variant, so requesting it fails as a `TranslationError`. A protected parameter is rejected with `ConfigError`, even though OMC 1.27 would accept it.

Decided in [Caching builds across sweep points](https://github.com/phdorp/modelica-tools/issues/50).
