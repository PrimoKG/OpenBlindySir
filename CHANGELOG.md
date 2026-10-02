# Changelog

All notable changes to OpenBlindySir are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While
the version is 0.x, the API and protocol may change between minor versions.

## [Unreleased]

### Added

- Project documentation: README, design specification, contribution guidelines,
  security policy and code of conduct.
- MIT license.

### Changed

- A warmer, consistent game interface for joining, audio setup, answers, host review
  and results, with clearer actions and layouts for phones and computers.
- Host settings, connection details and diagnostics are grouped behind accessible
  disclosures so the current round stays central.

### Fixed

- Host access now asks for elevation again after ending a session and joining a new one.
- Clip completion is shown during the remaining answer time, including after an early stop.
