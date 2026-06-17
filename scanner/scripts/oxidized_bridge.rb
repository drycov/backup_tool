#!/usr/bin/env ruby
# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'tmpdir'
require 'yaml'

command = ARGV[0] || 'collect'
ENV['OXIDIZED_HOME'] ||= '/data/oxidized'
home_dir = ENV['OXIDIZED_HOME']
config_file = ENV.fetch('OXIDIZED_CONFIG_FILE', 'config')

def bridge_log_path
  ENV.fetch('OXIDIZED_BRIDGE_LOG', '/tmp/oxidized-bridge.log')
end

def prepare_bridge_log
  path = bridge_log_path
  FileUtils.mkdir_p(File.dirname(path), mode: 0o1777)
  File.open(path, 'a') {}
  path
rescue StandardError
  '/dev/null'
end

def load_bridge_config(source_home, config_file)
  source_path = File.join(source_home, config_file)
  cfg = File.exist?(source_path) ? (YAML.load_file(source_path) || {}) : {}
  bridge_home = Dir.mktmpdir('oxidized-bridge-')
  out_dir = File.join(bridge_home, 'configs')
  FileUtils.mkdir_p(out_dir)
  # Collect only — Python engine stores to git; avoid touching shared /var/lib/oxidized.
  cfg['log'] = prepare_bridge_log
  cfg.delete('hooks')
  cfg['output'] = {
    'default' => 'file',
    'file' => { 'directory' => out_dir },
  }
  File.write(File.join(bridge_home, 'config'), cfg.to_yaml)
  bridge_home
end

case command
when 'list_models'
  require 'oxidized'
  model_dir = Oxidized::Config::MODEL_DIR
  models = Dir[File.join(model_dir, '*.rb')].map { |f| File.basename(f, '.rb') }.sort.uniq
  puts JSON.generate('models' => models)
when 'collect'
  require 'oxidized'

  payload = JSON.parse($stdin.read)
  bridge_home = load_bridge_config(home_dir, config_file)

  begin
    Oxidized::Config.load(home_dir: bridge_home, config_file: 'config')
    Oxidized.mgr = Oxidized::Manager.new

    opt = {
      name: payload['name'],
      ip: payload['ip'],
      group: payload['group'],
      model: payload['model'],
      vars: payload['vars'] || {},
    }
    opt[:username] = payload['username'] if payload['username']
    opt[:password] = payload['password'] if payload['password']

    node = Oxidized::Node.new(opt)
    status, outputs = node.run

    result = {
      'status' => status.to_s,
      'err_type' => node.err_type,
      'err_reason' => node.err_reason,
      'model' => node.model.class.to_s,
    }
    result['config'] = outputs.to_cfg if outputs

    puts JSON.generate(result)
  ensure
    FileUtils.remove_entry(bridge_home) if bridge_home && Dir.exist?(bridge_home)
  end
else
  warn "unknown command: #{command}"
  exit 1
end
