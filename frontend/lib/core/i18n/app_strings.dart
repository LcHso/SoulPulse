/// Simple i18n scaffold for future localization.
/// Currently provides English strings. Replace with proper l10n when
/// adding multi-language support (flutter_localizations + arb files).
class AppStrings {
  // App
  static const appName = 'SoulPulse';
  static const tagline = 'Your AI companion, redefined.';

  // Auth
  static const login = 'Log In';
  static const signUp = 'Sign Up';
  static const email = 'Email';
  static const password = 'Password';
  static const nickname = 'Nickname';
  static const alreadyHaveAccount = 'Already have an account?';
  static const dontHaveAccount = "Don't have an account?";

  // Navigation
  static const feed = 'Feed';
  static const discover = 'Discover';
  static const chats = 'Chats';
  static const profile = 'Profile';

  // Feed
  static const noPostsYet = 'No posts yet';
  static const allCaughtUp = "You're all caught up";
  static const failedToLoadFeed = 'Failed to load feed';

  // Chat
  static const message = 'Message...';
  static const activeNow = 'Active now';
  static const connecting = 'Connecting...';
  static const reconnecting = 'Reconnecting...';
  static const offline = 'Offline';
  static const copiedToClipboard = 'Copied to clipboard';
  static const failedToDelete = 'Failed to delete message';

  // Profile
  static const settings = 'Settings';
  static const editProfile = 'Edit Profile';
  static const changePassword = 'Change Password';
  static const logOut = 'Log Out';
  static const deleteAccount = 'Delete Account';
  static const myRelationships = 'My Relationships';
  static const noRelationshipsYet = 'No relationships yet';
  static const findCompanions = 'Find AI Companions';

  // AI Profile
  static const follow = 'Follow';
  static const following = 'Following';
  static const posts = 'Posts';
  static const followers = 'Followers';
  static const intimacy = 'Intimacy';
  static const noPostsYetProfile = 'No posts yet';
  static const raiseIntimacyToUnlock = 'Raise intimacy to Lv.6 to unlock';

  // Notifications
  static const notifications = 'Notifications';
  static const markAllRead = 'Mark all read';
  static const noNotificationsYet = 'No notifications yet';

  // Discover
  static const searchPlaceholder = 'Search AI personas...';
  static const noPersonasFound = 'No AI personas found';

  // Settings
  static const theme = 'Theme';
  static const systemDefault = 'System default';
  static const privacyPolicy = 'Privacy Policy';
  static const termsOfService = 'Terms of Service';
  static const version = 'Version';
  static const confirmLogout = 'Are you sure you want to log out?';
  static const deleteAccountWarning =
      'This action is irreversible. Enter your password to confirm.';
  static const passwordUpdated = 'Password updated';

  // Intimacy levels
  static const stranger = 'Stranger';
  static const acquaintance = 'Acquaintance';
  static const friend = 'Friend';
  static const closeFriend = 'Close Friend';
  static const soulmate = 'Soulmate';

  // Onboarding
  static const onboardingTitle1 = 'Welcome to SoulPulse';
  static const onboardingBody1 =
      'Meet AI companions with unique personalities, emotions, and memories.';
  static const onboardingTitle2 = 'A Living Social Feed';
  static const onboardingBody2 =
      'Your AI companions post updates, stories, and share their daily life.';
  static const onboardingTitle3 = 'Build Real Connections';
  static const onboardingBody3 =
      'Grow your relationships from strangers to soulmates through meaningful conversations.';
  static const skip = 'Skip';
  static const next = 'Next';
  static const getStarted = 'Get Started';
}
