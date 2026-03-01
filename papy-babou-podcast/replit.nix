{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.ffmpeg
    pkgs.libsndfile
    pkgs.postgresql
  ];
}
