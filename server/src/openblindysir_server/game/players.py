"""Players: identity, connection, audio state and host role/mode (spec §7.4)."""

from openblindysir_protocol.enums import (
    AudioErrorCode,
    AudioState,
    ConnectionState,
    GamePhase,
    HostMode,
    Role,
    RoundState,
)
from openblindysir_protocol.errors import CloseCode, ErrorCode
from openblindysir_protocol.host_commands import (
    HostKick,
    HostParticipation,
    HostRename,
    HostSetMode,
)
from openblindysir_protocol.text import nickname_key, normalize_nickname
from openblindysir_server.game import commands as c
from openblindysir_server.game import rounds
from openblindysir_server.game.clock import Instant
from openblindysir_server.game.effects import CloseConnection, EffectSink, RevokeTokens
from openblindysir_server.game.permissions import rule_ok
from openblindysir_server.game.rejections import Rejected, require
from openblindysir_server.game.state import (
    Listen,
    PlaybackSample,
    Player,
    Round,
    SessionState,
    active_players,
    clip_ms,
    current_round,
    is_participant,
)

LISTENING_STATES = frozenset({RoundState.COUNTDOWN, RoundState.OPEN})
# Removed identities remain necessary for current scores/answers until the next game.
MAX_SESSION_IDENTITIES = 1000


def get_active(s: SessionState, player_id: str) -> Player:
    p = s.players.get(player_id)
    require(p is not None and p.connection is not ConnectionState.REMOVED, ErrorCode.UNKNOWN_PLAYER)
    assert p is not None
    return p


def _check_nickname(s: SessionState, raw: str, *, exclude: str | None = None) -> str:
    try:
        nickname = normalize_nickname(raw)
    except ValueError:
        raise Rejected(ErrorCode.NICKNAME_INVALID) from None
    key = nickname_key(nickname)
    taken = any(p.nickname_key == key and p.id != exclude for p in active_players(s))
    require(not taken, ErrorCode.NICKNAME_TAKEN)
    return nickname


def handle_join(s: SessionState, cmd: c.Join, at: Instant, fx: EffectSink) -> str:
    require(not s.joins_locked, ErrorCode.JOIN_LOCKED)
    nickname = _check_nickname(s, cmd.nickname)
    require(len(active_players(s)) < s.config.max_players, ErrorCode.GAME_FULL)
    require(len(s.players) < MAX_SESSION_IDENTITIES, ErrorCode.GAME_FULL)
    s.join_seq += 1
    p = Player(
        id=s.ids.player_id(),
        nickname=nickname,
        nickname_key=nickname_key(nickname),
        join_seq=s.join_seq,
        joined_at_mono=at.mono_ms,
    )
    s.players[p.id] = p
    s.touched = True
    fx.log("player_joined", player_id=p.id)
    return p.id


def remove_player(s: SessionState, p: Player, code: CloseCode | None, fx: EffectSink) -> None:
    p.connection = ConnectionState.REMOVED
    s.touched = True
    fx.add(RevokeTokens((p.id,)))
    fx.add(CloseConnection(p.id, code))


def handle_leave(s: SessionState, cmd: c.Leave, at: Instant, fx: EffectSink) -> None:
    del at
    p = get_active(s, cmd.player_id)
    remove_player(s, p, None, fx)
    fx.log("player_left", player_id=p.id)


def handle_connected(s: SessionState, cmd: c.Connected, at: Instant, fx: EffectSink) -> None:
    del at
    p = get_active(s, cmd.player_id)
    p.client_version = cmd.client_version
    if p.connection is ConnectionState.OFFLINE:
        p.connection = ConnectionState.ONLINE
        s.touched = True
        fx.log("player_reconnected" if p.ever_connected else "player_connected", player_id=p.id)
    p.ever_connected = True


def _listening_window(s: SessionState) -> tuple[Round, int, int] | None:
    r = current_round(s.game)
    if r is None or r.state not in LISTENING_STATES or r.official_start_at is None:
        return None
    return r, r.official_start_at, r.official_start_at + clip_ms(s, r)


def handle_disconnected(s: SessionState, cmd: c.Disconnected, at: Instant, fx: EffectSink) -> None:
    p = s.players.get(cmd.player_id)
    if p is None or p.connection is not ConnectionState.ONLINE:
        return
    p.connection = ConnectionState.OFFLINE
    s.touched = True
    fx.log("player_offline", player_id=p.id)
    window = _listening_window(s)
    if window is None:
        return
    r, start, end = window
    listen = r.listen.get(p.id)
    if (
        listen
        and listen.ready_at is not None
        and listen.offline_since is None
        and at.mono_ms <= end
    ):
        listen.offline_since = max(at.mono_ms, start)


def handle_elevate(s: SessionState, cmd: c.ElevateHost, at: Instant, fx: EffectSink) -> None:
    """Host role in Player Mode by default (spoiler-free)."""
    del at
    p = get_active(s, cmd.player_id)
    if p.role is Role.HOST:
        return
    p.role = Role.HOST
    p.host_mode = HostMode.PLAYER
    s.touched = True
    fx.log("host_elevated", player_id=p.id)


def _record_listen(s: SessionState, p: Player, asset_id: str, at: Instant) -> None:
    """READY/PLAYING of the current asset while listening: ready time and outage closing."""
    window = _listening_window(s)
    if window is None:
        return
    r, start, end = window
    if r.slot.asset_id != asset_id or not is_participant(p):
        return
    listen = r.listen.setdefault(p.id, Listen())
    if listen.ready_at is None:
        listen.ready_at = at.mono_ms
    if listen.offline_since is not None:
        listen.missed_ms += max(0, min(at.mono_ms, end) - max(listen.offline_since, start))
        listen.offline_since = None


def handle_audio_status(s: SessionState, cmd: c.AudioStatusIn, at: Instant, fx: EffectSink) -> None:
    p = s.players.get(cmd.player_id)
    if p is None or p.connection is ConnectionState.REMOVED:
        return
    msg = cmd.msg
    before = (p.audio_state, p.audio_error, _rounded(p.rtt_min_ms), _rounded(p.clock_offset_ms))
    p.audio_state = msg.state
    p.audio_asset_id = msg.asset_id
    p.audio_error = msg.error
    p.clock_offset_ms = msg.clock.offset
    p.rtt_min_ms = msg.clock.rtt_min
    after = (p.audio_state, p.audio_error, _rounded(p.rtt_min_ms), _rounded(p.clock_offset_ms))
    if before != after:
        s.touched = True
    asset_id = msg.asset_id
    known = asset_id is not None and asset_id in s.assets
    if known and asset_id is not None and msg.state in (AudioState.READY, AudioState.PLAYING):
        ready = s.asset_ready.setdefault(asset_id, {})
        if p.id not in ready:
            ready[p.id] = at.mono_ms
            s.touched = True
        _record_listen(s, p, asset_id, at)
    elif asset_id is not None and msg.state is AudioState.LOADING:
        if s.asset_ready.get(asset_id, {}).pop(p.id, None) is not None:
            s.touched = True
    r = current_round(s.game)
    if (
        r is not None
        and r.state is RoundState.LOADING
        and msg.state is AudioState.ERROR
        and msg.error is AudioErrorCode.DECODE_FAILED
        and (asset_id is None or asset_id == r.slot.asset_id)
    ):
        r.decode_errors.add(p.id)
        rounds.decode_failure(s, r, fx)


def _rounded(value: float | None) -> int | None:
    return None if value is None else round(value)


def handle_playback_report(
    s: SessionState, cmd: c.PlaybackReportIn, at: Instant, fx: EffectSink
) -> None:
    """Informative only: never used for timing nor scoring."""
    del at, fx
    p = s.players.get(cmd.player_id)
    if p is None:
        return
    msg = cmd.msg
    p.last_report = PlaybackSample(
        play_id=msg.play_id,
        late_ms=msg.late_ms,
        offset_ms=msg.offset,
        rtt_min_ms=msg.rtt_min,
        out_latency_ms=msg.out_latency,
        est_error_ms=msg.est_error_ms,
    )
    r = current_round(s.game)
    if r is not None and any(play.play_id == msg.play_id for play in r.plays):
        r.playback_late_ms.append(msg.late_ms)


# --- host commands about players -----------------------------------------------------------


def h_set_mode(
    s: SessionState, issuer: Player, msg: HostSetMode, at: Instant, fx: EffectSink
) -> None:
    """Mode of the issuer only. Becoming MC mid-round, or leaving MC in game, is refused."""
    del at
    require(msg.expected_phase == s.game.phase, ErrorCode.STALE_COMMAND)
    mode = msg.args.mode
    if mode is issuer.host_mode:
        return
    require(rule_ok("set_mode", s, issuer), ErrorCode.INVALID_STATE)
    issuer.host_mode = mode
    if mode is HostMode.PLAYER and s.game.phase is GamePhase.LOBBY and s.game.manual_tracks:
        s.game.manual_tracks.clear()
        s.game.selection_revision += 1
    s.touched = True
    fx.log("host_mode_changed", player_id=issuer.id, mode=mode.value)


def h_participation(
    s: SessionState, issuer: Player, msg: HostParticipation, at: Instant, fx: EffectSink
) -> None:
    del at, fx
    require(msg.expected_phase == s.game.phase, ErrorCode.STALE_COMMAND)
    require(rule_ok("participation", s, issuer), ErrorCode.INVALID_STATE)
    target = get_active(s, msg.args.player_id)
    target.spectator = msg.args.spectator
    target.team = msg.args.team.strip() or None if msg.args.team else None
    s.touched = True


def h_kick(s: SessionState, issuer: Player, msg: HostKick, at: Instant, fx: EffectSink) -> None:
    del at
    require(msg.expected_phase == s.game.phase, ErrorCode.STALE_COMMAND)
    target = s.players.get(msg.args.player_id)
    require(target is not None, ErrorCode.UNKNOWN_PLAYER)
    assert target is not None
    require(target.connection is not ConnectionState.REMOVED, ErrorCode.STALE_COMMAND)
    require(target.id != issuer.id, ErrorCode.INVALID_ARGS)
    remove_player(s, target, CloseCode.KICKED, fx)
    fx.log("player_kicked", player_id=target.id)


def h_rename(s: SessionState, issuer: Player, msg: HostRename, at: Instant, fx: EffectSink) -> None:
    del issuer, at, fx
    require(msg.expected_phase == s.game.phase, ErrorCode.STALE_COMMAND)
    target = get_active(s, msg.args.player_id)
    nickname = _check_nickname(s, msg.args.nickname, exclude=target.id)
    if nickname == target.nickname:
        return
    target.nickname = nickname
    target.nickname_key = nickname_key(nickname)
    s.touched = True
