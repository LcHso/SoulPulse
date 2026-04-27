"""
Emotion Engine Tests

Tests for the emotion state machine core functions:
- Value clamping
- Time decay calculations
- Interaction effects
- Caring intent detection
- Chat event classification
- Proactive trigger conditions
"""

import pytest
from datetime import datetime, timezone, timedelta

from services import emotion_engine
from models.emotion_state import EmotionState


class TestClamp:
    """Tests for value clamping function."""

    def test_clamp_within_range(self):
        """Test value within range is unchanged."""
        result = emotion_engine._clamp(5.0, 0.0, 10.0)
        assert result == 5.0

    def test_clamp_below_range(self):
        """Test value below range is clamped to min."""
        result = emotion_engine._clamp(-5.0, 0.0, 10.0)
        assert result == 0.0

    def test_clamp_above_range(self):
        """Test value above range is clamped to max."""
        result = emotion_engine._clamp(15.0, 0.0, 10.0)
        assert result == 10.0

    def test_clamp_at_boundary(self):
        """Test value at boundary is unchanged."""
        assert emotion_engine._clamp(0.0, 0.0, 10.0) == 0.0
        assert emotion_engine._clamp(10.0, 0.0, 10.0) == 10.0


class TestClampState:
    """Tests for emotion state clamping."""

    def test_clamp_state_normal_values(self):
        """Test normal values are unchanged."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=50.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.5,
            security=0.4,
        )
        result = emotion_engine._clamp_state(state)
        
        assert result.energy == 50.0
        assert result.pleasure == 0.3
        assert result.activation == 0.2
        assert result.longing == 0.5
        assert result.security == 0.4

    def test_clamp_state_extreme_values(self):
        """Test extreme values are clamped to valid ranges."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=150.0,  # Over max (100)
            pleasure=-1.5,  # Below min (-1)
            activation=1.5,  # Over max (1)
            longing=-0.5,  # Below min (0)
            security=2.0,  # Over max (1)
        )
        result = emotion_engine._clamp_state(state)
        
        assert result.energy == 100.0
        assert result.pleasure == -1.0
        assert result.activation == 1.0
        assert result.longing == 0.0
        assert result.security == 1.0


class TestApplyTimeDecay:
    """Tests for time decay calculations."""

    def test_decay_no_last_interaction(self):
        """Test decay when no last interaction is set."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=50.0,
            pleasure=0.5,
            activation=0.5,
            longing=0.0,
            security=0.5,
            last_interaction_at=None,
        )
        
        result = emotion_engine.apply_time_decay(state)
        
        assert result.last_interaction_at is not None

    def test_decay_energy_recovery(self):
        """Test that energy recovers over time."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=20.0,
            pleasure=0.0,
            activation=0.0,
            longing=0.0,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        
        result = emotion_engine.apply_time_decay(state)
        
        # Energy should recover +5 per hour
        assert result.energy >= 25.0

    def test_decay_longing_increases(self):
        """Test that longing increases over time."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.0,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        
        result = emotion_engine.apply_time_decay(state)
        
        # Longing should increase +0.03 per hour
        assert result.longing >= 0.03

    def test_decay_pleasure_attenuates(self):
        """Test that pleasure attenuates toward 0."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.8,
            activation=0.5,
            longing=0.0,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(hours=10),
        )
        
        result = emotion_engine.apply_time_decay(state)
        
        # Pleasure should decay toward 0
        assert result.pleasure < 0.8
        assert result.pleasure > 0  # Still positive

    def test_decay_max_hours_capped(self):
        """Test that decay is capped at max hours."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=0.0,  # Low energy
            pleasure=0.5,
            activation=0.5,
            longing=0.0,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=365),  # 1 year ago
        )
        
        result = emotion_engine.apply_time_decay(state)
        
        # Energy should be capped at max recovery (5 * 168 hours = 840, capped at 100)
        assert result.energy <= 100.0
        # Longing should be capped
        assert result.longing <= 1.0


class TestApplyInteraction:
    """Tests for interaction effects on emotion state."""

    def test_apply_chat_interaction(self):
        """Test chat interaction effect."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.5,
            security=0.4,
        )
        
        result = emotion_engine.apply_interaction(state, "chat")
        
        # Chat consumes energy, increases pleasure/activation/security, reduces longing
        assert result.energy == 77.0  # -3
        assert abs(result.pleasure - 0.35) < 0.001  # +0.05
        assert abs(result.activation - 0.25) < 0.001  # +0.05
        assert abs(result.longing - 0.25) < 0.001  # * 0.5
        assert abs(result.security - 0.42) < 0.001  # +0.02

    def test_apply_chat_caring_interaction(self):
        """Test caring chat interaction effect."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=50.0,
            pleasure=0.3,
            activation=0.5,
            longing=0.8,
            security=0.3,
        )
        
        result = emotion_engine.apply_interaction(state, "chat_caring")
        
        # Caring chat restores energy, increases pleasure/security significantly
        assert result.energy == 62.0  # +12
        assert abs(result.pleasure - 0.4) < 0.001  # +0.10
        assert abs(result.activation - 0.45) < 0.001  # -0.05
        assert abs(result.longing - 0.16) < 0.001  # * 0.2
        assert abs(result.security - 0.38) < 0.001  # +0.08

    def test_apply_like_interaction(self):
        """Test like interaction effect."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.5,
            security=0.4,
        )
        
        result = emotion_engine.apply_interaction(state, "like")
        
        # Like doesn't consume energy, increases pleasure/security
        assert result.energy == 80.0  # 0 change
        assert abs(result.pleasure - 0.35) < 0.001  # +0.05
        assert abs(result.activation - 0.21) < 0.001  # +0.01
        assert abs(result.longing - 0.47) < 0.001  # -0.03
        assert abs(result.security - 0.43) < 0.001  # +0.03

    def test_apply_unknown_event(self):
        """Test unknown event doesn't crash."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.5,
            security=0.4,
        )
        
        result = emotion_engine.apply_interaction(state, "unknown_event")
        
        # Should return unchanged state
        assert result.energy == 80.0
        assert result.pleasure == 0.3


class TestDetectCaringIntent:
    """Tests for caring intent detection."""

    def test_detect_caring_chinese(self):
        """Test detecting Chinese caring keywords."""
        keywords = ["早睡", "晚安", "好好休息", "注意身体"]
        for kw in keywords:
            assert emotion_engine.detect_caring_intent(f"你要{kw}") == True

    def test_detect_caring_english(self):
        """Test detecting English caring keywords."""
        keywords = ["rest well", "good night", "take care", "sleep well"]
        for kw in keywords:
            assert emotion_engine.detect_caring_intent(f"You should {kw}") == True

    def test_detect_non_caring(self):
        """Test that non-caring messages return False."""
        messages = [
            "Hello",
            "How are you?",
            "What's the weather?",
            "Tell me a story",
        ]
        for msg in messages:
            assert emotion_engine.detect_caring_intent(msg) == False


class TestClassifyChatEvent:
    """Tests for chat event classification."""

    def test_classify_caring_message(self):
        """Test that caring messages are classified as chat_caring."""
        result = emotion_engine.classify_chat_event("你要好好休息")
        assert result == "chat_caring"

    def test_classify_long_message(self):
        """Test that long messages are classified as chat_long."""
        long_message = "a" * 101  # Over 100 characters
        result = emotion_engine.classify_chat_event(long_message)
        assert result == "chat_long"

    def test_classify_normal_message(self):
        """Test that normal messages are classified as chat."""
        result = emotion_engine.classify_chat_event("Hello")
        assert result == "chat"


class TestBuildEmotionDirective:
    """Tests for emotion directive generation."""

    def test_build_directive_high_energy(self):
        """Test directive with high energy."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=90.0,
            pleasure=0.5,
            activation=0.3,
            longing=0.1,
            security=0.5,
        )
        
        result = emotion_engine.build_emotion_directive(state)
        
        assert "full of energy" in result.lower()
        assert "Energy: 90" in result

    def test_build_directive_low_energy(self):
        """Test directive with low energy."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=15.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.1,
            security=0.5,
        )
        
        result = emotion_engine.build_emotion_directive(state)
        
        assert "exhausted" in result.lower()

    def test_build_directive_high_longing(self):
        """Test directive includes longing when significant."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.8,  # High longing
            security=0.5,
        )
        
        result = emotion_engine.build_emotion_directive(state)
        
        assert "missed" in result.lower()

    def test_build_directive_low_security(self):
        """Test directive includes insecurity when low."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.1,
            security=-0.3,  # Low security
        )
        
        result = emotion_engine.build_emotion_directive(state)
        
        assert "insecure" in result.lower()


class TestGetParamOverrides:
    """Tests for generation parameter overrides."""

    def test_param_overrides_low_energy(self):
        """Test short replies with low energy."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=15.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.1,
            security=0.5,
        )
        
        result = emotion_engine.get_param_overrides(state)
        
        assert result["max_tokens_factor"] == 0.4

    def test_param_overrides_high_energy(self):
        """Test full replies with high energy."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.1,
            security=0.5,
        )
        
        result = emotion_engine.get_param_overrides(state)
        
        assert result["max_tokens_factor"] == 1.0

    def test_param_overrides_high_activation(self):
        """Test temperature increase with high activation."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.5,
            activation=0.7,  # High activation
            longing=0.1,
            security=0.5,
        )
        
        result = emotion_engine.get_param_overrides(state)
        
        assert result["temperature_delta"] == 0.05

    def test_param_overrides_low_activation(self):
        """Test temperature decrease with low activation."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.5,
            activation=-0.7,  # Low activation
            longing=0.1,
            security=0.5,
        )
        
        result = emotion_engine.get_param_overrides(state)
        
        assert result["temperature_delta"] == -0.05


class TestCheckProactiveTriggers:
    """Tests for proactive trigger conditions."""

    def test_welcome_dm_trigger(self):
        """Test welcome_dm trigger for new users."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.0,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc),
        )
        
        result = emotion_engine.check_proactive_triggers(
            state,
            intimacy=1.5,  # In range 1-3
            has_sent_welcome=False,
        )
        
        assert "welcome_dm" in result

    def test_welcome_dm_not_triggered_already_sent(self):
        """Test welcome_dm not triggered if already sent."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.0,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc),
        )
        
        result = emotion_engine.check_proactive_triggers(
            state,
            intimacy=1.5,
            has_sent_welcome=True,  # Already sent
        )
        
        assert "welcome_dm" not in result

    def test_daily_checkin_trigger(self):
        """Test daily_checkin trigger after 24h."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.0,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        
        result = emotion_engine.check_proactive_triggers(
            state,
            intimacy=3.0,  # >= 2
        )
        
        assert "daily_checkin" in result

    def test_longing_dm_trigger(self):
        """Test longing_dm trigger with high longing."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.8,  # > 0.7
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc),
        )
        
        result = emotion_engine.check_proactive_triggers(
            state,
            intimacy=6.0,  # >= 5
        )
        
        assert "longing_dm" in result

    def test_moody_story_trigger(self):
        """Test moody_story trigger with low energy and pleasure."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=25.0,  # < 30
            pleasure=-0.5,  # < -0.3
            activation=0.0,
            longing=0.0,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc),
        )
        
        result = emotion_engine.check_proactive_triggers(
            state,
            intimacy=4.0,  # >= 3
        )
        
        assert "moody_story" in result

    def test_enthusiastic_post_trigger(self):
        """Test enthusiastic_post trigger with high pleasure and activation."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.7,  # > 0.6
            activation=0.6,  # > 0.5
            longing=0.0,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc),
        )
        
        result = emotion_engine.check_proactive_triggers(
            state,
            intimacy=4.0,  # >= 3
        )
        
        assert "enthusiastic_post" in result

    def test_no_triggers(self):
        """Test no triggers when conditions not met."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.1,
            security=0.5,
            last_interaction_at=datetime.now(timezone.utc),
        )
        
        result = emotion_engine.check_proactive_triggers(
            state,
            intimacy=1.0,  # Too low for most triggers
            has_sent_welcome=True,
        )
        
        assert len(result) == 0


class TestBuildEmotionHint:
    """Tests for emotion hint building for frontend."""

    def test_emotion_hint_tired(self):
        """Test hint for tired energy level."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=20.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.5,
            security=0.5,
        )
        
        result = emotion_engine.build_emotion_hint(state)
        
        assert result["energy_level"] == "tired"
        assert "mood" in result

    def test_emotion_hint_normal(self):
        """Test hint for normal energy level."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=50.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.5,
            security=0.5,
        )
        
        result = emotion_engine.build_emotion_hint(state)
        
        assert result["energy_level"] == "normal"

    def test_emotion_hint_energetic(self):
        """Test hint for energetic energy level."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=85.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.5,
            security=0.5,
        )
        
        result = emotion_engine.build_emotion_hint(state)
        
        assert result["energy_level"] == "energetic"

    def test_emotion_hint_longing(self):
        """Test hint shows longing when significant."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.7,
            security=0.5,
        )
        
        result = emotion_engine.build_emotion_hint(state)
        
        assert result["longing"] == True

    def test_emotion_hint_no_longing(self):
        """Test hint shows no longing when low."""
        state = EmotionState(
            user_id=1,
            ai_id=1,
            energy=80.0,
            pleasure=0.3,
            activation=0.2,
            longing=0.3,
            security=0.5,
        )
        
        result = emotion_engine.build_emotion_hint(state)
        
        assert result["longing"] == False
