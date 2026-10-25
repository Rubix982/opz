# Points the AWS provider at the local emulator (moto). On a real account you'd
# delete the endpoint overrides and the fake keys, and nothing else changes.
variable "aws_endpoint" {
  type    = string
  default = "http://aws:5000"
}

provider "aws" {
  region     = "us-east-1"
  access_key = "testing" # moto's dummy credentials, not real
  secret_key = "testing"

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    ec2 = var.aws_endpoint
    s3  = var.aws_endpoint
    sts = var.aws_endpoint
    iam = var.aws_endpoint
  }
}
