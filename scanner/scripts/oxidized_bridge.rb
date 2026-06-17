#!/usr/bin/env ruby
# frozen_string_literal: true

require 'json'

command = ARGV[0] || 'collect'
ENV['OXIDIZED_HOME'] ||= '/data/oxidized'
home_dir = ENV['OXIDIZED_HOME']
config_file = ENV.fetch('OXIDIZED_CONFIG_FILE', 'config')

case command
when 'list_models'
  require 'oxidized'
  model_dir = Oxidized::Config::MODEL_DIR
  models = Dir[File.join(model_dir, '*.rb')].map { |f| File.basename(f, '.rb') }.sort.uniq
  puts JSON.generate('models' => models)
when 'collect'
  require 'oxidized'

  payload = JSON.parse($stdin.read)

  Oxidized::Config.load(home_dir: home_dir, config_file: config_file)
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
else
  warn "unknown command: #{command}"
  exit 1
end
