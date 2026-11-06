# The key that encrypts people's model keys, memory and chats.
resource "aws_kms_key" "user_keys" {
  description             = "${local.name_prefix}: users' model API keys"
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

resource "aws_kms_alias" "user_keys" {
  name          = "alias/${local.name_prefix}-user-keys"
  target_key_id = aws_kms_key.user_keys.key_id
}
