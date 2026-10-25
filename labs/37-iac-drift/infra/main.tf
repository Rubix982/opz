# The web tier's security group and the bucket nightly reports land in.

resource "aws_security_group" "web" {
  name        = "web"
  description = "Public web tier"

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name  = "web"
    owner = "platform"
    env   = "prod"
  }
}

resource "aws_s3_bucket" "reports" {
  bucket = "opz-lab37-reports"

  tags = {
    owner = "data"
    env   = "prod"
  }
}

# Reports are overwritten nightly; versioning is how last week's is recovered.
resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration {
    status = "Enabled"
  }
}
